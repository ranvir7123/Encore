"""Task 12: `encore` CLI entry point (pyproject.toml: encore = "encore.cli:main").

Seven subcommands, argparse-based:
  encore eval       --seeds 100,101,102 --customers 500   -> runs the matrix, writes runs/eval.json
  encore report                                            -> reads runs/eval.json, writes runs/scoreboard.html
  encore parse-eval                                        -> keyword vs haiku vs sonnet accuracy on data/reply_eval.jsonl
  encore demo       --n 3 --timeout 300 --dry-run          -> Task 11's Razorpay demo slice
  encore web                                               -> writes web/data/*.json + web/py/*.py
  encore seed-live  --n 2                                  -> N real original links for the live slice
  encore agent      --batch 50 --live 2 [--dry-run]        -> the recovery loop, board at runs/board.html
"""
import argparse
import functools
import glob
import json
import os
import random
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv

from encore.agent import RecoveryAgent
from encore.audit import AttemptLedger, AuditLog
from encore.board import build_board, write_board
from encore.clock import InstantClock, SimClock
from encore.demo import run_demo_slice
from encore.domain import DeclineCode
from encore.evaluate import EVAL_HORIZON_HOURS, REGIMES, run_matrix
from encore.parser import evaluate as parser_evaluate
from encore.parser import parse_keyword, parse_llm
from encore.policies import PromiseAwarePolicy, RandomInHorizon
from encore.rails import RazorpayLinkRail, SimulatedAgentRail
from encore.razorpay_client import RazorpayClient
from encore.report import write_scoreboard
from encore.simulator import Portfolio
from encore.sources import (
    IST_OFFSET_S,
    RazorpayCaptureWatch,
    RazorpayFailureSource,
    SimulatedFailureSource,
)
from encore.wall import WallConfig
from encore.webdata import build_cliff, build_results
from encore.webhtml import render_page


def cmd_eval(args: argparse.Namespace) -> None:
    seeds = [int(s) for s in args.seeds.split(",")]
    out_dir = Path(args.out_dir)
    results = run_matrix(seeds=seeds, out_dir=out_dir, n_customers=args.customers)
    print(f"Ran {len(results)} regime/policy cells over seeds {seeds}, "
          f"{args.customers} customers each.")
    print(f"Wrote {out_dir / 'eval.json'}")


def cmd_report(args: argparse.Namespace) -> None:
    out_path = write_scoreboard(
        eval_path=Path(args.eval_path), out_path=Path(args.out_path),
        audit_dir=Path(args.audit_dir),
    )
    print(f"Wrote {out_path}")


def cmd_parse_eval(args: argparse.Namespace) -> None:
    load_dotenv()  # picks up ANTHROPIC_API_KEY from .env if present, same as demo.py does for Razorpay
    eval_path = Path(args.eval_path)
    keyword_result = parser_evaluate(parse_keyword, eval_path)
    print(f"keyword       : accuracy_kind={keyword_result['accuracy_kind']:.3f} "
          f"accuracy_full={keyword_result['accuracy_full']:.3f} (n={keyword_result['n']})")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set -- skipping claude-haiku-4-5 and "
              "claude-sonnet-5 scoring, printing keyword-only accuracy above.")
        return

    for model in ("claude-haiku-4-5", "claude-sonnet-5"):
        # strict: an API failure raises here rather than silently scoring the
        # keyword fallback under the model's name
        result = parser_evaluate(functools.partial(parse_llm, model=model, strict=True), eval_path)
        print(f"{model:14s}: accuracy_kind={result['accuracy_kind']:.3f} "
              f"accuracy_full={result['accuracy_full']:.3f} (n={result['n']})")


# The modules Pyodide fetches and imports at runtime (Tier A). Every one of
# them imports only the standard library plus its siblings here -- that is what
# makes the browser tier possible at all, so the list is deliberately explicit
# rather than a glob over src/encore: adding model.py to it would silently drag
# scikit-learn into the page and break the deploy at load time, not at build.
TIER_A_MODULES = ["__init__", "domain", "wall", "audit", "simulator", "policies", "scheduler"]

# The cliff chart is about the held-out distribution shift specifically.
CLIFF_REGIME = "r1_shifted"
CLIFF_POLICIES = ["encore_learned", "random_in_horizon"]


def _read_executions(audit_dir: Path, regime: str, policy: str) -> list[dict]:
    """All execution records for one regime/policy, across every seed's audit
    log. Returns [] when nothing matches, so a partial runs/ directory produces
    an empty chart with a visible provenance line rather than a crash."""
    records: list[dict] = []
    pattern = str(audit_dir / f"{regime}__{policy}__s*_audit.jsonl")
    for path in sorted(glob.glob(pattern)):
        records.extend(AuditLog(Path(path)).read_all())
    return records


def cmd_web(args: argparse.Namespace) -> None:
    eval_path = Path(args.eval_path)
    if not eval_path.exists():
        raise SystemExit(
            f"{eval_path} not found -- run `encore eval --seeds {args.seeds} "
            f"--customers {args.customers}` first. runs/ is gitignored scratch, so a "
            "fresh clone or worktree has none of it."
        )
    seeds = [int(s) for s in args.seeds.split(",")]
    eval_dict = json.loads(eval_path.read_text(encoding="utf-8"))

    out_dir = Path(args.out_dir)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    results = build_results(eval_dict, seeds=seeds, customers=args.customers)
    (data_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    audit_dir = Path(args.audit_dir)
    executions = {p: _read_executions(audit_dir, CLIFF_REGIME, p) for p in CLIFF_POLICIES}
    cliff = build_cliff(executions, regime=CLIFF_REGIME, seeds=seeds, customers=args.customers)
    (data_dir / "cliff.json").write_text(
        json.dumps(cliff, indent=2, ensure_ascii=False), encoding="utf-8")

    # index.html is RENDERED from a hand-written template rather than hand-written
    # itself. Tier B has to be complete before any JavaScript runs (spec section 3),
    # which means the cliff chart's ~120 numbers live in the markup -- and hand-
    # transcribing them is exactly the failure the spec calls a transcription bug.
    # The template holds all the prose and structure; only measured values are
    # substituted, and an unfilled marker raises rather than shipping "{{CELLS}}".
    template_path = Path(args.template)
    if template_path.exists():
        page = render_page(
            template_path.read_text(encoding="utf-8"),
            results, cliff, test_count=args.test_count,
        )
        (out_dir / "index.html").write_text(page, encoding="utf-8")
        print(f"Wrote {out_dir / 'index.html'} from {template_path}")

    # Copy the live modules next to the page so the deploy is self-contained:
    # the site fetches these over HTTP and writes them into the Pyodide FS, so
    # publishing web/ without them would 404 the whole Tier A panel.
    py_dir = out_dir / "py"
    py_dir.mkdir(parents=True, exist_ok=True)
    src_dir = Path(args.src_dir)
    for module in TIER_A_MODULES:
        shutil.copyfile(src_dir / f"{module}.py", py_dir / f"{module}.py")

    print(f"Wrote {data_dir / 'results.json'} ({results['totals']['cells']} cells, "
          f"{results['totals']['compliance_violations']} violations)")
    for policy in CLIFF_POLICIES:
        series = cliff["series"][policy]
        print(f"Wrote cliff series {policy}: {series['total_tried']} retries, "
              f"{series['total_won']} recovered")
    print(f"Copied {len(TIER_A_MODULES)} live modules to {py_dir}")


def _ist_midnight(now_ts: int) -> int:
    """Unix timestamp of the most recent 00:00 IST -- the anchor that maps a
    real failure's timestamp onto the agent's simulated-hour axis."""
    local = now_ts + IST_OFFSET_S
    return local - (local % 86400) - IST_OFFSET_S


def cmd_seed_live(args: argparse.Namespace) -> None:
    """Create N real test-mode Payment Links standing in for the ORIGINAL
    debits of N synthetic customers. The operator fails them on checkout;
    `encore agent --live N` then detects those failures through the Payments
    API, with the customer carried on the payment's notes."""
    load_dotenv()
    client = RazorpayClient()
    world = Portfolio.generate(args.customers, REGIMES[args.regime], seed=args.seed)
    failures = [f for f in SimulatedFailureSource(world, "live").failures()
                if f.decline is DeclineCode.INSUFFICIENT_FUNDS][:args.n]
    stamp = int(time.time())
    created = []
    for f in failures:
        ref = f"{f.customer_id}:live:original:{stamp}"
        link = client.create_payment_link(
            f.amount_paise, f"FAIL THIS ONE - Encore original debit for {f.customer_id}", ref,
            notes={"customer_id": f.customer_id, "cycle_id": "live", "kind": "original"})
        created.append({"customer_id": f.customer_id, "amount_paise": f.amount_paise,
                        "link_id": link["id"], "short_url": link["short_url"],
                        "reference_id": ref})
        print(f"{f.customer_id}  INR {f.amount_paise / 100:.2f}  {link['short_url']}")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "live_originals.json").write_text(json.dumps(created, indent=2), encoding="utf-8")
    print(f"\nWrote {out_dir / 'live_originals.json'} ({len(created)} link(s)).")
    print("Fail each link on checkout: contact 9123456789, Cards, 4100 2800 0008 0001\n"
          "(insufficient funds), any CVV, any future expiry. If a mock bank page\n"
          "appears, click Failure. Then run: encore agent --live", len(created))


def cmd_agent(args: argparse.Namespace) -> None:
    dry = args.dry_run
    live_n = 0 if dry else args.live
    out_dir = Path(args.out_dir)
    suffix = "_dryrun" if dry else ""
    audit = AuditLog(out_dir / f"agent_audit{suffix}.jsonl")
    ledger = AttemptLedger(out_dir / f"agent_ledger{suffix}.txt")
    board_path = out_dir / f"board{suffix}.html"

    world = Portfolio.generate(args.customers, REGIMES[args.regime], seed=args.seed)
    all_failures = SimulatedFailureSource(world, f"agent_s{args.seed}").failures()

    live_failures, unmapped, live_rail, live_ids, capture_watch = [], [], None, set(), None
    if live_n > 0:
        load_dotenv()
        client = RazorpayClient()
        now_ts = int(time.time())
        source = RazorpayFailureSource(client, now_ts - args.window_s, now_ts,
                                       _ist_midnight(now_ts))
        live_failures = source.failures()[:live_n]
        unmapped = source.unmapped
        live_ids = {f.customer_id for f in live_failures}
        live_rail = RazorpayLinkRail(client)
        watch = RazorpayCaptureWatch(client, now_ts - args.window_s)

        def capture_watch(ids: set[str]) -> dict[str, dict]:
            # a customer paying the ORIGINAL demand after the nudge is a
            # recovery too, and ends their sequence (BROKELOG entry 15)
            return watch.captured(ids, int(time.time()))
        print(f"Payments API: {len(live_failures)} mapped failure(s), "
              f"{len(unmapped)} unmapped, in the last {args.window_s // 60} min.")

    batch = [f for f in all_failures if f.customer_id not in live_ids][:args.batch]
    batch_ids = {f.customer_id for f in batch}
    replies = [r for r in world.reply_events() if r.customer_id in batch_ids]
    at_risk = {f.customer_id: f.amount_paise for f in batch + live_failures}
    at_risk.update({u["customer_id"]: u["amount_paise"] for u in unmapped})

    # The shipped policy is the best MEASURED one in runs/eval.json: the parsed
    # promise when there is one, uniform-random inside the compliant window
    # otherwise, on a seeded stream so a rerun replays the same hours.
    policy = PromiseAwarePolicy(
        RandomInHorizon(random.Random(args.seed), max_hour=EVAL_HORIZON_HOURS),
        max_hour=EVAL_HORIZON_HOURS, name="promise_aware_random")
    provenance = (f"seed {args.seed} | regime {args.regime} | {len(batch)} simulated + "
                  f"{len(live_failures)} live on Razorpay test mode | policy {policy.name} | "
                  f"{args.speed} sim-hours per second | {'DRY RUN' if dry else 'live'}")
    printed = {"links": 0}

    def on_tick(agent: RecoveryAgent, result) -> None:
        write_board(board_path, build_board(agent.records, at_risk), provenance)
        links = [r for r in agent.records if r["event"] == "link_created"]
        for r in links[printed["links"]:]:
            # The timeout is sized for a HUMAN paying a link, not for software
            # (BROKELOG entry 14): say when it expires, in wall-clock time.
            pay_by = time.strftime("%H:%M:%S", time.localtime(time.time() + args.timeout))
            print(f"  LINK for {r['customer_id']} INR {r['amount_paise'] / 100:.2f}: "
                  f"{r.get('short_url')}  ({r.get('link_id')})  pay by {pay_by}")
        printed["links"] = len(links)

    clock = SimClock(1.0 / args.speed) if args.speed > 0 else InstantClock()
    agent = RecoveryAgent(WallConfig(), policy, SimulatedAgentRail(world), audit, ledger, clock,
                          live_rail=live_rail, live_customers=frozenset(live_ids),
                          poll_interval_s=args.interval, timeout_s=args.timeout, on_tick=on_tick,
                          capture_watch=capture_watch)
    print(f"=== Encore recovery agent{' (DRY RUN)' if dry else ''} ===\n{provenance}\n"
          f"board: {board_path}\n")
    result = agent.run(batch + live_failures, replies, unmapped)
    rate = (result.recovered_paise / result.at_risk_paise * 100) if result.at_risk_paise else 0.0
    print(f"\nat risk     INR {result.at_risk_paise / 100:,.2f}")
    print(f"recovered   INR {result.recovered_paise / 100:,.2f}  ({rate:.1f}%)")
    print(f"attempts {result.attempts_executed}  denied {result.attempts_denied}  "
          f"nudges {result.nudges_sent}  duplicates_blocked {result.duplicates_blocked}  "
          f"paid_on_their_own {result.self_cured}")
    print("parked: " + (", ".join(f"{k}={v}" for k, v in sorted(result.parked.items())) or "none"))
    print(f"audit: {audit.path}  ledger: {ledger.path}  board: {board_path}")



def cmd_demo(args: argparse.Namespace) -> None:
    if not args.dry_run:
        load_dotenv()  # RazorpayClient reads RAZORPAY_KEY_ID/SECRET from the environment
    run_demo_slice(n=args.n, timeout_s=args.timeout_s, interval_s=args.interval_s,
                   dry_run=args.dry_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="encore", description="Encore CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("eval", help="run the regime x policy eval matrix, write runs/eval.json")
    p_eval.add_argument("--seeds", default="100,101,102",
                        help="comma-separated eval seeds (default: 100,101,102)")
    p_eval.add_argument("--customers", type=int, default=500,
                        help="customers per seed (default: 500)")
    p_eval.add_argument("--out-dir", default="runs", help="output directory (default: runs)")
    p_eval.set_defaults(func=cmd_eval)

    p_report = sub.add_parser("report", help="read runs/eval.json, write runs/scoreboard.html")
    p_report.add_argument("--eval-path", default="runs/eval.json")
    p_report.add_argument("--out-path", default="runs/scoreboard.html")
    p_report.add_argument("--audit-dir", default="runs")
    p_report.set_defaults(func=cmd_report)

    p_parse_eval = sub.add_parser(
        "parse-eval", help="score keyword vs claude-haiku-4-5 vs claude-sonnet-5 on data/reply_eval.jsonl")
    p_parse_eval.add_argument("--eval-path", default="data/reply_eval.jsonl")
    p_parse_eval.set_defaults(func=cmd_parse_eval)

    p_demo = sub.add_parser("demo", help="Task 11 Razorpay demo slice")
    p_demo.add_argument("--n", type=int, default=3, help="number of soft-decline failures (default: 3)")
    p_demo.add_argument("--timeout", type=int, default=300, dest="timeout_s",
                        help="poll_until_terminal timeout in seconds (default: 300)")
    p_demo.add_argument("--interval", type=int, default=5, dest="interval_s",
                        help="poll interval in seconds (default: 5)")
    p_demo.add_argument("--dry-run", action="store_true",
                        help="exercise the full code path against SimulatedRail -- no network")
    p_demo.set_defaults(func=cmd_demo)

    p_web = sub.add_parser("web", help="build web/data/*.json and web/py/*.py from runs/")
    p_web.add_argument("--eval-path", default="runs/eval.json")
    p_web.add_argument("--audit-dir", default="runs")
    p_web.add_argument("--out-dir", default="web")
    p_web.add_argument("--src-dir", default="src/encore")
    p_web.add_argument("--seeds", default="100,101,102",
                       help="seeds the eval was run with, for the provenance line")
    p_web.add_argument("--customers", type=int, default=500,
                       help="customers per seed the eval was run with, for the provenance line")
    p_web.add_argument("--template", default="web/index.template.html",
                       help="hand-written page template; measured values are substituted in")
    p_web.add_argument("--test-count", type=int, default=153,
                       help="suite size quoted in the hero (keep in step with `uv run pytest -q`)")
    p_web.set_defaults(func=cmd_web)

    p_seed = sub.add_parser("seed-live",
                            help="create N real original test-mode links for the live slice")
    p_seed.add_argument("--n", type=int, default=2)
    p_seed.add_argument("--seed", type=int, default=100)
    p_seed.add_argument("--regime", default="r1_shifted", choices=sorted(REGIMES))
    p_seed.add_argument("--customers", type=int, default=500)
    p_seed.add_argument("--out-dir", default="runs")
    p_seed.set_defaults(func=cmd_seed_live)

    p_agent = sub.add_parser("agent", help="run the recovery agent; board at runs/board.html")
    p_agent.add_argument("--batch", type=int, default=50,
                         help="simulated failures to work (default: 50)")
    p_agent.add_argument("--live", type=int, default=0,
                         help="real failed payments to work on Razorpay test mode (default: 0)")
    p_agent.add_argument("--seed", type=int, default=100)
    p_agent.add_argument("--regime", default="r1_shifted", choices=sorted(REGIMES))
    p_agent.add_argument("--customers", type=int, default=500)
    p_agent.add_argument("--speed", type=float, default=2.0,
                         help="simulated hours per real second; 0 = instant (default: 2)")
    p_agent.add_argument("--interval", type=float, default=5.0,
                         help="seconds between polls of a live link (default: 5)")
    p_agent.add_argument("--timeout", type=float, default=600.0,
                         help="seconds to wait for a HUMAN to pay a live link (default: 600)")
    p_agent.add_argument("--window-s", type=int, default=3 * 3600, dest="window_s",
                         help="how far back to look for failed payments (default: 3h)")
    p_agent.add_argument("--out-dir", default="runs")
    p_agent.add_argument("--dry-run", action="store_true",
                         help="everything on the simulator, no network; forces --live 0")
    p_agent.set_defaults(func=cmd_agent)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
