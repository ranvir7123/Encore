from pathlib import Path

from encore.audit import AttemptLedger, AuditLog
from encore.domain import DeclineCode
from encore.policies import FixedSchedule, ImmediateRetry3
from encore.scheduler import Scheduler, SimulatedRail
from encore.simulator import Portfolio, RegimeConfig
from encore.wall import WallConfig

R0 = RegimeConfig(salary_days=[1, 7, 15], salary_day_weights=[0.6, 0.3, 0.1],
                  hard_decline_rate=0.08, issuer_down_daily_prob=0.05)


def build_world(seed=42):
    p = Portfolio.generate(300, R0, seed=seed)
    # 30 days = one billing per customer; a 60-day world bills twice under one cycle_id (see BROKELOG 2026-08-31)
    failures = p.run_cycle(30, "c1")
    return p, failures


def run(policy, tmp_path: Path, p, failures):
    sched = Scheduler(WallConfig())
    return sched.run(p, failures, policy,
                     SimulatedRail(p),
                     AuditLog(tmp_path / "audit.jsonl"),
                     AttemptLedger(tmp_path / "ledger.txt"))


def test_fixed_schedule_recovers_some_money(tmp_path):
    p, failures = build_world()
    result = run(FixedSchedule(), tmp_path, p, failures)
    assert result.recovered_paise > 0
    assert result.attempts_executed > 0


def test_no_hard_decline_is_ever_executed(tmp_path):
    p, failures = build_world()
    run(FixedSchedule(), tmp_path, p, failures)
    log = AuditLog(tmp_path / "audit.jsonl").read_all()
    hard_customers = {f.customer_id for f in failures
                     if f.decline in {DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED,
                                      DeclineCode.RISK_DECLINED}}
    executed = {r["customer_id"] for r in log if r["event"] == "execution"}
    assert not (hard_customers & executed)


def test_rerun_with_same_ledger_executes_nothing_new(tmp_path):
    p, failures = build_world()
    first = run(FixedSchedule(), tmp_path, p, failures)
    p2, failures2 = build_world()  # fresh world state, SAME ledger on disk
    second = run(FixedSchedule(), tmp_path, p2, failures2)
    assert first.attempts_executed > 0
    assert second.attempts_executed == 0  # idempotency held across "crash restart"


def test_immediate_retry_burns_attempts_on_window_denials(tmp_path):
    p, failures = build_world()
    result = run(ImmediateRetry3(), tmp_path, p, failures)
    assert result.denials_by_reason.get("outside_execution_window", 0) > 0
