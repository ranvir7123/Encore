"""The recovery agent loop, dry run: InstantClock, simulated rail, tmp_path
audit and ledger. Every legality question still goes through wall.decide();
these tests pin what the loop does with replies, hard declines, unmapped
failures and a shared ledger."""
from pathlib import Path

from encore.agent import RecoveryAgent
from encore.audit import AttemptLedger, AuditLog
from encore.clock import InstantClock
from encore.domain import DeclineCode, day_of_month
from encore.parser import ReplyIntent
from encore.policies import FixedSpread10, PromiseAwarePolicy
from encore.rails import SimulatedAgentRail
from encore.simulator import Portfolio, RegimeConfig, ReplyEvent
from encore.wall import WallConfig

R1 = RegimeConfig([3, 10, 25], [0.2, 0.3, 0.5], 0.15, 0.12)
HARD = {DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED, DeclineCode.RISK_DECLINED}


def _world(seed=100, n=200):
    p = Portfolio.generate(n, R1, seed=seed)
    return p, p.run_cycle(30, "agent")


def _agent(tmp_path: Path, p, **kw):
    policy = PromiseAwarePolicy(FixedSpread10(max_hour=720), max_hour=720)
    agent = RecoveryAgent(WallConfig(), policy, SimulatedAgentRail(p),
                          AuditLog(tmp_path / "a.jsonl"), AttemptLedger(tmp_path / "l.txt"),
                          InstantClock(), **kw)
    return agent, policy


def test_batch_recovers_money_and_every_sequence_ends_in_exactly_one_terminal_event(tmp_path):
    p, failures = _world()
    agent, _ = _agent(tmp_path, p)
    result = agent.run(failures, p.reply_events())
    assert result.recovered_paise > 0
    assert result.at_risk_paise == sum(f.amount_paise for f in failures)
    wins = sum(1 for r in agent.records if r["event"] == "execution" and r["outcome"] == "success")
    parked = sum(1 for r in agent.records if r["event"] == "park")
    dupes = sum(1 for r in agent.records if r["event"] == "duplicate_blocked")
    assert wins + parked + dupes == len(failures)
    assert result.recovered_paise == sum(r["amount_paise"] for r in agent.records
                                         if r["event"] == "execution" and r["outcome"] == "success")


def test_hard_declines_are_parked_as_hard_decline_terminal_and_never_executed(tmp_path):
    p, failures = _world()
    hard = {f.customer_id for f in failures if f.decline in HARD}
    agent, _ = _agent(tmp_path, p)
    agent.run(failures, [])
    executed = {r["customer_id"] for r in agent.records if r["event"] == "execution"}
    assert hard and not (hard & executed)
    assert {r["customer_id"] for r in agent.records
            if r["event"] == "park" and r["reason"] == "hard_decline_terminal"} == hard


def test_cancel_reply_kills_the_sequence_before_any_execution(tmp_path):
    p, failures = _world()
    f = next(x for x in failures if x.decline is DeclineCode.INSUFFICIENT_FUNDS)
    agent, _ = _agent(tmp_path, p)
    agent.run([f], [ReplyEvent(f.customer_id, f.at_hour + 2, "cancel karo yeh subscription")])
    assert not [r for r in agent.records if r["event"] == "execution"]
    assert [r["reason"] for r in agent.records if r["event"] == "park"] == ["sequence_killed"]


def test_promise_reply_moves_the_retry_to_the_promised_day(tmp_path):
    p, failures = _world()
    f = next(x for x in failures
             if x.decline is DeclineCode.INSUFFICIENT_FUNDS and x.at_hour < 5 * 24)
    agent, policy = _agent(tmp_path, p)
    agent.run([f], [ReplyEvent(f.customer_id, f.at_hour + 3,
                               "salary 25 tarikh ko aayegi, tab try karna")])
    assert policy.promises[f.customer_id] == 25
    first = next(r for r in agent.records if r["event"] == "execution")
    assert day_of_month(first["at_hour"]) == 25


def test_dispute_reply_parks_with_reason_dispute(tmp_path):
    p, failures = _world()
    f = next(x for x in failures if x.decline is DeclineCode.INSUFFICIENT_FUNDS)
    agent, _ = _agent(tmp_path, p, parse_fn=lambda text: ReplyIntent(kind="dispute"))
    agent.run([f], [ReplyEvent(f.customer_id, f.at_hour + 3, "maine yeh kabhi liya hi nahi")])
    assert [r["reason"] for r in agent.records if r["event"] == "park"] == ["dispute"]
    assert not [r for r in agent.records if r["event"] == "execution"]


def test_unmapped_failures_are_parked_and_counted_at_risk(tmp_path):
    p, _ = _world()
    agent, _ = _agent(tmp_path, p)
    result = agent.run([], [], unmapped=[{"payment_id": "pay_9", "customer_id": "rzp:pay_9",
                                         "error_reason": "card_declined", "amount_paise": 49900}])
    assert result.parked == {"unmapped_error_reason": 1} and result.at_risk_paise == 49900


def test_rerun_with_the_same_ledger_executes_nothing_new(tmp_path):
    p, failures = _world()
    agent, _ = _agent(tmp_path, p)
    first = agent.run(failures, [])
    p2, failures2 = _world()
    agent2, _ = _agent(tmp_path, p2)
    second = agent2.run(failures2, [])
    assert first.attempts_executed > 0 and second.attempts_executed == 0
    assert second.duplicates_blocked > 0


def test_nudge_is_sent_once_per_failure_and_gated_by_the_wall(tmp_path):
    p, failures = _world()
    agent, _ = _agent(tmp_path, p)
    result = agent.run(failures, [])
    assert result.nudges_sent == len(failures)
    assert sum(1 for r in agent.records if r["event"] == "nudge") == len(failures)
