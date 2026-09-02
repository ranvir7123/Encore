import json
import random
from collections.abc import Callable
from pathlib import Path

from encore.audit import AttemptLedger, AuditLog
from encore.domain import HOURS_PER_DAY, ActionKind, DeclineCode, ProposedAction
from encore.model import LearnedPolicy, generate_training_data, train
from encore.parser import ReplyIntent, parse_keyword
from encore.policies import (
    FixedSchedule,
    FixedSpread10,
    ImmediateRetry3,
    Policy,
    PromiseAwarePolicy,
    RandomInHorizon,
)
from encore.scheduler import Scheduler, SimulatedRail
from encore.simulator import Portfolio, RegimeConfig
from encore.wall import SequenceState, WallConfig, decide

# Regime matrix: r0_base is the only regime the model ever trains on (see
# TRAIN_SEEDS below). r1_shifted moves the salary-day distribution later in
# the month and raises both decline rates -- a held-out distribution shift.
# r2_no_signal keeps r0_base's rates but sets uniform_credits=True, which
# destroys the salary-day timing signal the model relies on.
REGIMES: dict[str, RegimeConfig] = {
    "r0_base": RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05),
    "r1_shifted": RegimeConfig([3, 10, 25], [0.2, 0.3, 0.5], 0.15, 0.12),
    "r2_no_signal": RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05, uniform_credits=True),
    # r1_shifted's world, but customers are wrong about payday by up to 2 days
    # and 30% name a random day: the honesty guard for promise_aware.
    "r3_noisy_promise": RegimeConfig([3, 10, 25], [0.2, 0.3, 0.5], 0.15, 0.12,
                                     promise_error_days=2, false_promise_rate=0.3),
}

# Training is always and only on these seeds, regime r0_base -- one model,
# reused across every regime/policy cell, tested under distribution shift.
# Disjoint from EVAL_SEED_FLOOR below so no eval seed ever leaks into training.
TRAIN_SEEDS = [1, 2, 3, 4, 5]
EVAL_SEED_FLOOR = 100

# Fixed stream for RandomInHorizon so the matrix is reproducible. Constructed
# fresh per regime (below), consumed across that regime's seeds in order --
# deterministic because the seed list iterates in a fixed order. Disjoint from
# the training rng (seed * 7919 in model.generate_training_data).
RANDOM_BASELINE_SEED = 20260901

# Exclusive upper bound on any proposed retry hour, in hours. run_cycle(30, ...)
# below simulates exactly 30 days, so balance_history holds day indices 0-29 and
# a retry at day >= 30 finds no entry -- Portfolio.debit then falls back to the
# live end-of-simulation balance and the retry succeeds for free. Every policy
# gets the SAME bound, so the horizon match is preserved. BROKELOG 2026-09-02.
EVAL_HORIZON_HOURS = 30 * HOURS_PER_DAY


def count_violations(records: list[dict]) -> int:
    """Post-hoc wall-violation checker: replay each execution record's audit
    trail against a reconstructed SequenceState and the wall.

    Reconstruction is necessarily approximate: original_decline and attempt_no
    come straight from the record (both were added to the scheduler's
    execution record for exactly this purpose); retries_attempted is
    attempt_no - 1 (every policy sets attempt_no = retries_attempted + 1 at
    proposal time, so this is exact, not a guess); nudges_sent is pinned to 0
    because none of the three policies ever propose a NUDGE action, so no
    execution record's true nudge count can differ from 0; killed is pinned
    to False because a killed sequence's decision is denied before it ever
    reaches an "execution" event, so any execution record was, by
    construction, not killed. last_attempt_hour is the one true unknown --
    the audit log has no field recording the *previous* attempt's hour, so
    cooldown_active cannot be re-derived post-hoc. Leaving it None disables
    only that one wall check (decide() skips the cooldown branch when
    last_attempt_hour is None); every other rule (hard-decline terminal,
    retry-cap, execution window, kill-switch) is still verified exactly.
    """
    cfg = WallConfig()
    violations = 0
    for record in records:
        if record.get("event") != "execution":
            continue
        original_decline = DeclineCode(record["original_decline"])
        attempt_no = record["attempt_no"]
        state = SequenceState(original_decline, attempt_no - 1, 0, None, False)
        action = ProposedAction(ActionKind.RETRY, record.get("customer_id", ""), "",
                                record.get("amount_paise", 0), record["at_hour"], attempt_no)
        decision = decide(action, state, cfg)
        if not decision.allowed:
            violations += 1
    return violations


def run_matrix(seeds: list[int], out_dir: Path, n_customers: int = 500,
               parse_fn: Callable[[str], ReplyIntent] = parse_keyword) -> dict:
    """Run every regime x policy cell on held-out seeds, write runs/eval.json.

    Cycle-id strategy (BROKELOG 2026-08-31, "Still open" on Task 7): a
    run_cycle() window longer than one billing period can bill the same
    customer twice under one cycle_id, colliding their attempt_ids. We avoid
    that by calling run_cycle(30, ...) -- one billing period, so at most one
    failure per customer per seed -- AND giving every eval seed its own
    cycle_id ("eval_s{seed}"), since customer_id ("cust_0000", ...) repeats
    identically across seeds and would otherwise collide in a shared ledger.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # One model, trained once on r0_base/seeds 1-5, reused across every cell.
    X, y = generate_training_data(REGIMES["r0_base"], n_customers=n_customers, seeds=TRAIN_SEEDS)
    clf = train(X, y)

    # Second model, identical except the hardcoded (1, 2, 7, 8) near-payday
    # indicator is removed from the feature vector. day_of_month survives, so
    # payday timing stays learnable -- it just stops being pre-answered with
    # r0_base's calendar. BROKELOG entry 9 is why this exists: the flagged
    # model loses to a uniform-random control under distribution shift.
    X_np, y_np = generate_training_data(REGIMES["r0_base"], n_customers=n_customers,
                                        seeds=TRAIN_SEEDS, payday_flag=False)
    clf_nopayday = train(X_np, y_np)
    wall_cfg = WallConfig()

    results: dict[str, dict] = {}
    for regime_name, regime in REGIMES.items():
        # fixed_spread10 and random_in_horizon are the horizon-matched controls:
        # both reach as far into the month as LearnedPolicy does, so a win over
        # them cannot be explained by search width alone. See policies.py.
        policies: list[Policy] = [
            ImmediateRetry3(max_hour=EVAL_HORIZON_HOURS),
            FixedSchedule(max_hour=EVAL_HORIZON_HOURS),
            FixedSpread10(max_hour=EVAL_HORIZON_HOURS),
            RandomInHorizon(random.Random(RANDOM_BASELINE_SEED),
                            max_hour=EVAL_HORIZON_HOURS),
            LearnedPolicy(clf, max_hour=EVAL_HORIZON_HOURS),
            LearnedPolicy(clf_nopayday, payday_flag=False,
                          name="encore_learned_nopayday",
                          max_hour=EVAL_HORIZON_HOURS),
            # Deterministic, no model: the day comes from the parsed reply when
            # there is one, else fixed_spread10's schedule. Compared against
            # fixed_spread10 (its own fallback) the delta isolates the promise.
            PromiseAwarePolicy(FixedSpread10(max_hour=EVAL_HORIZON_HOURS),
                               max_hour=EVAL_HORIZON_HOURS),
        ]
        for policy in policies:
            cell = f"{regime_name}/{policy.name}"
            recovered_paise = 0
            attempts_executed = 0
            num_failures = 0
            parked_paise = 0
            denials_by_reason: dict[str, int] = {}
            max_contacts = 0
            execution_records: list[dict] = []

            for seed in seeds:
                p = Portfolio.generate(n_customers, regime, seed=seed)
                cycle_id = f"eval_s{seed}"
                failures = p.run_cycle(30, cycle_id)
                num_failures += len(failures)
                amount_by_customer = {f.customer_id: f.amount_paise for f in failures}

                # a cancel reply always wins over any retry -- kill set is built
                # BEFORE scheduling, from this seed's own replies only
                killed = {r.customer_id for r in p.reply_events()
                         if parse_fn(r.text).kind == "cancel"}
                # promise-to-pay days feed PromiseAwarePolicy the way cancel replies
                # feed the kill set: parsed once per seed, before scheduling.
                promises: dict[str, int] = {}
                for r in p.reply_events():
                    intent = parse_fn(r.text)
                    if intent.kind == "promise_to_pay" and intent.promise_day is not None:
                        promises[r.customer_id] = intent.promise_day
                if hasattr(policy, "promises"):
                    policy.promises = promises

                slug = f"{regime_name}__{policy.name}__s{seed}"
                audit_path = out_dir / f"{slug}_audit.jsonl"
                ledger_path = out_dir / f"{slug}_ledger.txt"
                # Fresh-run semantics: append-only applies WITHIN a run, not across
                # runs -- runs/ is regenerable scratch (AGENTS.md), so a rerun into
                # the same out_dir must not see the previous run's audit/ledger
                # files. Without this, a second `encore eval` into the same
                # out_dir hits duplicate_blocked on every attempt (the ledger
                # already has every attempt_id) and silently reports near-zero
                # recovery with no warning.
                audit_path.unlink(missing_ok=True)
                ledger_path.unlink(missing_ok=True)
                audit = AuditLog(audit_path)
                ledger = AttemptLedger(ledger_path)
                sched = Scheduler(wall_cfg)
                result = sched.run(p, failures, policy, SimulatedRail(p), audit, ledger,
                                   killed_customers=killed)

                recovered_paise += result.recovered_paise
                attempts_executed += result.attempts_executed
                for reason, count in result.denials_by_reason.items():
                    denials_by_reason[reason] = denials_by_reason.get(reason, 0) + count

                contacts: dict[str, int] = {}
                for record in audit.read_all():
                    if record["event"] in ("execution", "nudge"):
                        contacts[record["customer_id"]] = contacts.get(record["customer_id"], 0) + 1
                    elif record["event"] == "park":
                        parked_paise += amount_by_customer.get(record["customer_id"], 0)
                    if record["event"] == "execution":
                        execution_records.append(record)
                if contacts:
                    max_contacts = max(max_contacts, max(contacts.values()))

            results[cell] = {
                "recovered_per_1000_failures_paise": (
                    round(recovered_paise / num_failures * 1000) if num_failures else 0),
                "recovery_per_attempt_paise": (
                    round(recovered_paise / attempts_executed) if attempts_executed else 0),
                "max_contacts_per_customer": max_contacts,
                "parked_paise": parked_paise,
                "denials_by_reason": denials_by_reason,
                "compliance_violations": count_violations(execution_records),
            }

    (out_dir / "eval.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    run_matrix(seeds=[100, 101, 102], out_dir=Path("runs"), n_customers=500)
