"""Task 11: Razorpay demo slice -- real test-mode Payment Links driven by the
sequencer's own domain model (FailedDebit, ProposedAction, attempt_id,
AttemptLedger, AuditLog).

Bulk recovery metrics (Task 10's eval matrix, runs/eval.json) come entirely
from SimulatedRail -- a mocked debit against latent portfolio state. This
module proves the *rail integration itself* is real: it takes the first `n`
soft-decline failures from a seeded portfolio and, for each, creates one
genuine Razorpay test-mode Payment Link via RazorpayClient (reference_id =
attempt_id(action), so idempotency extends to the real rail through the same
AttemptLedger the simulator uses), then polls the real payment_links API
until the link reaches a terminal state or times out, writing outcomes into
the same audit-log format (AuditLog.append) the simulator writes.

See docs/spike-notes.md for the test-mode groundwork this design rests on --
in particular: no UPI on this account's checkout (Netbanking -> Razorpay's
mock bank page with explicit Success/Failure buttons instead), and a failed
payment attempt never moves a link's status off "created".

Run as: uv run python -m encore.demo [--n N] [--timeout S] [--interval S] [--dry-run]
"""
import argparse
from pathlib import Path

from dotenv import load_dotenv

from encore.audit import AttemptLedger, AuditLog
from encore.domain import ActionKind, ProposedAction, attempt_id
from encore.evaluate import EVAL_SEED_FLOOR, REGIMES
from encore.model import SOFT_CODES
from encore.parser import parse_keyword
from encore.razorpay_client import RazorpayClient, poll_until_terminal
from encore.scheduler import SimulatedRail
from encore.simulator import Portfolio
from encore.wall import SequenceState, WallConfig, decide

# Task 9/evaluate.py convention: TRAIN_SEEDS (1-5) are reserved for the
# model's training data and must never leak into any other run. Rather than
# invent a fresh seed, this demo reuses EVAL_SEED_FLOOR (100) -- the first
# seed in evaluate.py's disjoint eval-seed pool -- so every non-training run
# in this codebase draws from the same documented range.
DEMO_SEED = EVAL_SEED_FLOOR
DEMO_REGIME = "r0_base"
DEMO_N_CUSTOMERS = 500
DEMO_CYCLE_ID = f"demo_s{DEMO_SEED}"  # distinct from evaluate.py's "eval_s{seed}" cycle ids


class SimulatedRazorpayClient:
    """--dry-run stand-in for RazorpayClient. Duck-types the same two methods
    (create_payment_link / fetch_payment_link) so poll_until_terminal and
    run_demo_slice's control flow run completely unchanged -- only the
    network call is swapped out, per the brief's "--dry-run flag exercises
    the full code path against SimulatedRail (no network, no links)".

    The outcome is resolved synchronously inside create_payment_link (via
    SimulatedRail.execute, the same rail the simulator/eval harness uses),
    storing "paid" on success or "created" on failure -- mirroring the real
    API's actual behavior (docs/spike-notes.md: there is no real "failed"
    status; a failed attempt just never leaves "created"). Because the
    result is known immediately, fetch_payment_link never changes its
    answer across calls -- run_demo_slice compensates by forcing
    timeout_s=0 in dry-run mode (see run_demo_slice) so a simulated failure
    resolves to "no_terminal_status_within_timeout" on the first poll
    instead of sleeping for real wall-clock seconds to no purpose.
    """

    def __init__(self, portfolio: Portfolio, actions_by_reference: dict[str, ProposedAction]) -> None:
        self._rail = SimulatedRail(portfolio)
        self._actions = actions_by_reference
        self._links: dict[str, dict] = {}

    def create_payment_link(self, amount_paise: int, description: str, reference_id: str) -> dict:
        action = self._actions[reference_id]
        success = self._rail.execute(action)
        link_id = f"sim_{reference_id.replace(':', '_')}"
        link = {
            "id": link_id,
            "amount": amount_paise,
            "amount_paid": amount_paise if success else 0,
            "description": description,
            "reference_id": reference_id,
            "short_url": f"(dry-run, no network call -- {link_id})",
            "status": "paid" if success else "created",
        }
        self._links[link_id] = link
        return dict(link)

    def fetch_payment_link(self, link_id: str) -> dict:
        return dict(self._links[link_id])


def _first_n_soft_failures(n: int) -> tuple[Portfolio, list]:
    p = Portfolio.generate(DEMO_N_CUSTOMERS, REGIMES[DEMO_REGIME], seed=DEMO_SEED)
    failures = p.run_cycle(30, DEMO_CYCLE_ID)  # one billing period -- avoids the
    # double-billing/attempt_id-collision trap documented in BROKELOG 2026-08-31
    # ("Plan's own scheduler test fails...") and reused by evaluate.py.
    soft = [f for f in failures if f.decline in SOFT_CODES]
    return p, soft[:n]


def run_demo_slice(n: int = 3, timeout_s: int = 300, interval_s: int = 5,
                   dry_run: bool = False, out_dir: Path = Path("runs")) -> list[dict]:
    out_dir = Path(out_dir)
    # Dry-run writes to its own audit/ledger files so repeated `--dry-run`
    # verification runs never mix simulated records into the real demo's
    # audit trail, and can be re-run to demonstrate idempotency on their own.
    suffix = "_dryrun" if dry_run else ""
    audit = AuditLog(out_dir / f"demo_audit{suffix}.jsonl")
    ledger = AttemptLedger(out_dir / f"demo_ledger{suffix}.txt")

    portfolio, failures = _first_n_soft_failures(n)
    if len(failures) < n:
        print(f"WARNING: seed {DEMO_SEED} regime {DEMO_REGIME} only produced "
              f"{len(failures)} soft-decline failure(s), fewer than the {n} requested.")

    # Same kill-set construction as evaluate.py::run_matrix: a cancel reply
    # always wins over any retry, built BEFORE scheduling, from this seed's
    # own replies only.
    killed = {r.customer_id for r in portfolio.reply_events()
             if parse_keyword(r.text).kind == "cancel"}
    wall_cfg = WallConfig()

    planned = []  # (failed, action, aid)
    actions: dict[str, ProposedAction] = {}
    for failed in failures:
        # attempt_no=1, execute_at_hour=failed.at_hour + 72 (a T+3-days retry --
        # matches the product's actual retry framing, e.g. FixedSchedule's T+1/
        # T+2/T+3 shape). On the real rail this hour is inert bookkeeping: a
        # human pays the link whenever they click through, the API doesn't
        # consult it. But --dry-run's SimulatedRazorpayClient calls
        # SimulatedRail.execute(action), which (as of the time-aware rail fix,
        # commit 869cdcf/BROKELOG "Dry-run demo evidence went stale...") looks
        # up simulated balance at execute_at_hour via balance_history -- and
        # execute_at_hour=failed.at_hour would replay the debit at the EXACT
        # hour it already failed, deterministically re-failing every time.
        # +72h gives the simulated customer's balance a chance to have moved
        # (e.g. a later salary credit) by the hour the "retry" is dated to,
        # same as a real T+3 retry would. attempt_id does not include the
        # hour, so reference_ids and ledger/idempotency behavior are
        # unaffected by this change.
        action = ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                                failed.amount_paise, failed.at_hour + 72, 1)
        aid = attempt_id(action)
        actions[aid] = action
        planned.append((failed, action, aid))

    client = SimulatedRazorpayClient(portfolio, actions) if dry_run else RazorpayClient()

    print(f"\n=== Encore demo slice{' (DRY RUN -- simulated rail, no network)' if dry_run else ''} ===")
    print(f"seed={DEMO_SEED} regime={DEMO_REGIME} n_requested={n} n_available={len(failures)}\n")

    created = []  # entries with a live link: {failed, action, aid, link}
    for i, (failed, action, aid) in enumerate(planned, start=1):
        if ledger.already_executed(aid):
            print(f"[{i}] {aid}: already executed (ledger hit) -- skipping, no new link created.")
            audit.append({"event": "duplicate_blocked", "attempt_id": aid, "reference_id": aid})
            continue
        # Route through the same wall every scheduled attempt goes through --
        # attempt_no=1, no prior attempt (matches the fresh SequenceState the
        # scheduler builds for a never-before-seen failure); killed is the
        # only thing that can differ per customer here.
        state = SequenceState(failed.decline, 0, 0, None, failed.customer_id in killed)
        decision = decide(action, state, wall_cfg)
        audit.append({"event": "decision", "customer_id": action.customer_id,
                      "attempt_id": aid, "kind": str(action.kind),
                      "at_hour": action.execute_at_hour, "allowed": decision.allowed,
                      "reason": decision.reason, "policy": "demo"})
        if not decision.allowed:
            print(f"[{i}] {aid}: wall denied ({decision.reason}) -- skipping, no link created.")
            continue
        description = f"Encore demo: {failed.customer_id} soft-decline retry ({aid})"
        link = client.create_payment_link(failed.amount_paise, description, aid)
        # Crash gap: if the process dies between create_payment_link succeeding
        # and ledger.record(aid) running, the real link exists but the local
        # ledger never learns about it. A rerun would then attempt to create a
        # second link with the same reference_id -- Razorpay is expected to
        # reject that as a duplicate-reference_id error (unhandled here), not
        # silently double-create a link. Acceptable for an operator-watched
        # demo (the operator sees the crash and the error), not hardened
        # against for unattended/automated use.
        ledger.record(aid)
        created.append({"failed": failed, "action": action, "aid": aid, "link": link})
        print(f"[{i}] {aid}")
        print(f"    amount: INR {failed.amount_paise / 100:.2f} ({failed.amount_paise} paise)")
        print(f"    link:   {link['short_url']}")

    if not dry_run and created:
        print(
            "\nOperator instructions (real test-mode links -- see docs/spike-notes.md):\n"
            "  1. Open each URL printed above.\n"
            "  2. Enter a valid-shaped test mobile number (e.g. 9123456789) -- an\n"
            "     obviously-fake all-same-digit number is rejected server-side.\n"
            "  3. Choose Netbanking (NOT UPI -- no UPI option is offered on this\n"
            "     account's checkout, despite the standard Razorpay test-mode docs).\n"
            "  4. On Razorpay's simulated bank page, click Success or Failure.\n"
        )

    # Effective poll settings: a simulated outcome is resolved synchronously
    # inside create_payment_link and never changes on a later fetch, so real
    # wall-clock waiting serves no purpose in dry-run mode -- force a single
    # immediate check (timeout_s=0, interval_s=0) regardless of the CLI's
    # --timeout/--interval, so a simulated failure still correctly exercises
    # the "no_terminal_status_within_timeout" branch below, just instantly.
    poll_timeout_s = 0 if dry_run else timeout_s
    poll_interval_s = 0 if dry_run else interval_s
    if created:
        print(f"\nPolling {len(created)} link(s) (timeout={poll_timeout_s}s, "
              f"interval={poll_interval_s}s each)...\n")

    outcomes: list[dict] = []
    for entry in created:
        failed, aid, link = entry["failed"], entry["aid"], entry["link"]
        status = poll_until_terminal(client, link["id"], timeout_s=poll_timeout_s,
                                     interval_s=poll_interval_s)
        if status == "paid":
            outcome = "success"
        elif status in ("cancelled", "expired"):
            outcome = "failure"
        else:  # status is still "created" -- see poll_until_terminal's docstring
            outcome = "no_terminal_status_within_timeout"
        record = {
            "event": "execution",
            "customer_id": failed.customer_id,
            "attempt_id": aid,
            "reference_id": aid,
            "link_id": link["id"],
            "amount_paise": failed.amount_paise,
            "status": status,
            "outcome": outcome,
            "rail": "simulated" if dry_run else "razorpay_test_mode",
        }
        audit.append(record)
        outcomes.append(record)
        print(f"{aid}: status={status} outcome={outcome}")

    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Task 11: real test-mode Razorpay demo slice, driven by the sequencer.")
    parser.add_argument("--n", type=int, default=3,
                        help="number of soft-decline failures to demo (default: 3)")
    parser.add_argument("--timeout", type=int, default=300, dest="timeout_s",
                        help="poll_until_terminal timeout in seconds per link (default: 300)")
    parser.add_argument("--interval", type=int, default=5, dest="interval_s",
                        help="poll interval in seconds (default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="exercise the full code path against SimulatedRail -- no network, no real links")
    args = parser.parse_args()

    if not args.dry_run:
        load_dotenv()  # RazorpayClient reads RAZORPAY_KEY_ID/SECRET from the environment

    run_demo_slice(n=args.n, timeout_s=args.timeout_s, interval_s=args.interval_s,
                   dry_run=args.dry_run)


if __name__ == "__main__":
    main()
