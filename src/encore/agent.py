"""The live recovery loop.

Not Scheduler.run: that is the synchronous batch evaluator behind the eval
matrix. This loop interleaves a clock, customer replies, wall decisions and
rails that may answer "pending" while a human pays a real link. Every
legality question still goes to wall.decide(); every attempt still goes
through the same AttemptLedger; every event is appended to the same AuditLog
shape the scheduler writes, plus `rail` and the rail's receipt fields.
"""
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from encore.audit import AttemptLedger, AuditLog
from encore.clock import Clock
from encore.domain import ActionKind, FailedDebit, ProposedAction, attempt_id
from encore.parser import ReplyIntent, parse_keyword
from encore.policies import Policy
from encore.rails import AgentRail
from encore.simulator import ReplyEvent
from encore.wall import SequenceState, WallConfig, decide

TERMINAL_DENIALS = ("hard_decline_terminal", "sequence_killed", "retry_cap_exceeded")


@dataclass
class AgentResult:
    at_risk_paise: int = 0
    recovered_paise: int = 0
    attempts_executed: int = 0
    attempts_denied: int = 0
    nudges_sent: int = 0
    duplicates_blocked: int = 0
    parked: dict[str, int] = field(default_factory=dict)


@dataclass
class _Seq:
    failed: FailedDebit
    state: SequenceState
    started: bool = False
    disputed: bool = False
    next_action: ProposedAction | None = None
    pending: ProposedAction | None = None
    pending_since: float | None = None
    last_poll: float | None = None
    done: bool = False


class RecoveryAgent:
    def __init__(self, wall_cfg: WallConfig, policy: Policy, rail: AgentRail, audit: AuditLog,
                 ledger: AttemptLedger, clock: Clock,
                 parse_fn: Callable[[str], ReplyIntent] = parse_keyword,
                 live_rail: AgentRail | None = None,
                 live_customers: frozenset[str] = frozenset(),
                 poll_interval_s: float = 5.0, timeout_s: float = 180.0,
                 on_tick: Callable[["RecoveryAgent", AgentResult], None] | None = None) -> None:
        self.cfg, self.policy, self.rail = wall_cfg, policy, rail
        self.audit, self.ledger, self.clock = audit, ledger, clock
        self.parse_fn, self.live_rail, self.live_customers = parse_fn, live_rail, live_customers
        self.poll_interval_s, self.timeout_s, self.on_tick = poll_interval_s, timeout_s, on_tick
        self.records: list[dict] = []
        self.result = AgentResult()

    # -- bookkeeping -------------------------------------------------------
    def _log(self, record: dict) -> None:
        self.audit.append(record)
        self.records.append(record)

    def _rail_for(self, customer_id: str) -> AgentRail:
        if self.live_rail is not None and customer_id in self.live_customers:
            return self.live_rail
        return self.rail

    def _park(self, s: _Seq, reason: str) -> None:
        s.done, s.next_action = True, None
        self.result.parked[reason] = self.result.parked.get(reason, 0) + 1
        self._log({"event": "park", "customer_id": s.failed.customer_id,
                   "cycle_id": s.failed.cycle_id, "amount_paise": s.failed.amount_paise,
                   "reason": reason, "policy": self.policy.name})

    # -- the loop ----------------------------------------------------------
    def run(self, failures: list[FailedDebit], replies: list[ReplyEvent],
            unmapped: list[dict] = ()) -> AgentResult:
        result = self.result
        result.at_risk_paise = (sum(f.amount_paise for f in failures)
                                + sum(u["amount_paise"] for u in unmapped))
        for u in unmapped:
            # A failure we cannot classify is an exception to report, not a
            # retry to guess at. It never reaches the wall.
            result.parked["unmapped_error_reason"] = result.parked.get("unmapped_error_reason", 0) + 1
            self._log({"event": "park", "customer_id": u["customer_id"],
                       "reason": "unmapped_error_reason", "error_reason": u["error_reason"],
                       "payment_id": u["payment_id"], "amount_paise": u["amount_paise"],
                       "policy": self.policy.name})
        if len({f.customer_id for f in failures}) != len(failures):
            raise ValueError("one sequence per customer: duplicate customer_id in failures")
        seqs = {f.customer_id: _Seq(f, SequenceState(f.decline, 0, 0, None, False))
                for f in failures}
        replies = sorted(replies, key=lambda r: r.at_hour)
        ri = 0
        now = min((f.at_hour for f in failures), default=0)
        while True:
            self.clock.advance_to(now)
            while ri < len(replies) and replies[ri].at_hour <= now:
                self._handle_reply(seqs, replies[ri], now)
                ri += 1
            for s in seqs.values():
                if not s.done and not s.started and s.failed.at_hour <= now:
                    self._start(s, now)
            for s in seqs.values():
                if (not s.done and s.pending is None and s.next_action is not None
                        and s.next_action.execute_at_hour <= now):
                    self._execute(s, now)
            for s in seqs.values():
                if s.pending is not None:
                    self._poll(s, now)
            if self.on_tick:
                self.on_tick(self, result)
            if all(s.done for s in seqs.values()):
                return result
            due = [s.next_action.execute_at_hour for s in seqs.values()
                   if not s.done and s.pending is None and s.next_action is not None]
            due += [s.failed.at_hour for s in seqs.values() if not s.started]
            if ri < len(replies):
                due.append(replies[ri].at_hour)
            if any(s.pending is not None for s in seqs.values()):
                now += 1  # a live link is waiting on a human: creep one sim hour per poll
            elif due:
                now = max(now, min(due))
            else:
                return result

    # -- steps -------------------------------------------------------------
    def _start(self, s: _Seq, now: int) -> None:
        s.started = True
        nudge = ProposedAction(ActionKind.NUDGE, s.failed.customer_id, s.failed.cycle_id,
                               s.failed.amount_paise, now, 1)
        d = decide(nudge, s.state, self.cfg)
        self._log({"event": "decision", "customer_id": nudge.customer_id,
                   "attempt_id": attempt_id(nudge), "kind": str(nudge.kind), "at_hour": now,
                   "allowed": d.allowed, "reason": d.reason, "policy": self.policy.name})
        if d.allowed:
            self.result.nudges_sent += 1
            s.state = replace(s.state, nudges_sent=s.state.nudges_sent + 1)
            self._log({"event": "nudge", "customer_id": nudge.customer_id,
                       "attempt_id": attempt_id(nudge), "at_hour": now})
        # Ask the wall whether this sequence is retryable AT ALL before the
        # policy looks for a slot. A policy with no slot left in the window
        # would otherwise park a revoked mandate as "policy_stop", and the
        # exception list should carry the wall's reason, not the calendar's.
        probe_hour = (now // 24) * 24 + 23
        probe = ProposedAction(ActionKind.RETRY, s.failed.customer_id, s.failed.cycle_id,
                               s.failed.amount_paise, probe_hour, 1)
        verdict = decide(probe, s.state, self.cfg)
        self._log({"event": "decision", "customer_id": probe.customer_id,
                   "attempt_id": attempt_id(probe), "kind": str(probe.kind), "at_hour": probe_hour,
                   "allowed": verdict.allowed, "reason": verdict.reason,
                   "policy": self.policy.name, "probe": True})
        if not verdict.allowed and verdict.reason in TERMINAL_DENIALS:
            self.result.attempts_denied += 1
            self._park(s, verdict.reason)
            return
        self._plan(s, now)

    def _plan(self, s: _Seq, now: int) -> None:
        """Propose until the wall allows one, exactly as Scheduler.run does:
        non-terminal denials burn retry budget; terminal denials park."""
        while not s.done:
            base = max(now, s.state.last_attempt_hour or s.failed.at_hour)
            action = self.policy.propose(s.failed, s.state, base)
            if action is None:
                self._park(s, "policy_stop")
                return
            d = decide(action, s.state, self.cfg)
            self._log({"event": "decision", "customer_id": action.customer_id,
                       "attempt_id": attempt_id(action), "kind": str(action.kind),
                       "at_hour": action.execute_at_hour, "allowed": d.allowed,
                       "reason": d.reason, "policy": self.policy.name})
            if d.allowed:
                s.next_action = action
                return
            self.result.attempts_denied += 1
            if d.reason in TERMINAL_DENIALS:
                self._park(s, d.reason)
                return
            s.state = replace(s.state, retries_attempted=s.state.retries_attempted + 1,
                              last_attempt_hour=action.execute_at_hour)

    def _execute(self, s: _Seq, now: int) -> None:
        action = s.next_action
        aid = attempt_id(action)
        s.next_action = None
        if self.ledger.already_executed(aid):
            self.result.duplicates_blocked += 1
            self._log({"event": "duplicate_blocked", "attempt_id": aid,
                       "customer_id": action.customer_id})
            s.done = True
            return
        self.ledger.record(aid)
        rail = self._rail_for(action.customer_id)
        outcome = rail.execute(action)
        if outcome == "pending":
            s.pending, s.pending_since, s.last_poll = action, self.clock.monotonic(), None
            self._log({"event": "link_created", "customer_id": action.customer_id,
                       "attempt_id": aid, "at_hour": action.execute_at_hour,
                       "amount_paise": action.amount_paise, "rail": rail.name,
                       **rail.receipt(action)})
            return
        self._resolve(s, action, outcome, rail, now)

    def _poll(self, s: _Seq, now: int) -> None:
        rail = self._rail_for(s.failed.customer_id)
        t = self.clock.monotonic()
        if s.last_poll is not None and t - s.last_poll < self.poll_interval_s:
            return
        s.last_poll = t
        outcome = rail.poll(s.pending)
        if outcome == "pending":
            if t - s.pending_since >= self.timeout_s:
                # A failed attempt never moves a link off "created", so a
                # timeout is the only failure signal the link API gives us.
                self._resolve(s, s.pending, "failure", rail, now,
                              status="no_terminal_status_within_timeout")
            return
        self._resolve(s, s.pending, outcome, rail, now)

    def _resolve(self, s: _Seq, action: ProposedAction, outcome: str, rail: AgentRail,
                 now: int, status: str | None = None) -> None:
        s.pending = None
        self.result.attempts_executed += 1
        record = {"event": "execution", "customer_id": action.customer_id,
                  "attempt_id": attempt_id(action), "at_hour": action.execute_at_hour,
                  "outcome": outcome, "amount_paise": action.amount_paise,
                  "policy": self.policy.name, "original_decline": str(s.state.original_decline),
                  "attempt_no": action.attempt_no, "rail": rail.name, **rail.receipt(action)}
        if status:
            record["status"] = status
        self._log(record)
        if outcome == "success":
            self.result.recovered_paise += action.amount_paise
            s.done = True
            return
        s.state = replace(s.state, retries_attempted=s.state.retries_attempted + 1,
                          last_attempt_hour=action.execute_at_hour)
        if s.disputed:
            self._park(s, "dispute")
            return
        self._plan(s, max(now, action.execute_at_hour))

    def _handle_reply(self, seqs: dict[str, _Seq], reply: ReplyEvent, now: int) -> None:
        intent = self.parse_fn(reply.text)
        self._log({"event": "reply", "customer_id": reply.customer_id, "at_hour": reply.at_hour,
                   "text": reply.text, "kind": intent.kind, "promise_day": intent.promise_day})
        s = seqs.get(reply.customer_id)
        if s is None or s.done:
            return
        if intent.kind == "cancel":
            # The kill switch is a wall input, not an agent shortcut: mark the
            # state and let decide() answer sequence_killed on the next plan.
            s.state = replace(s.state, killed=True)
            if s.started and s.pending is None:
                s.next_action = None
                self._plan(s, now)
        elif intent.kind == "dispute":
            # Never chase a disputed charge. If a link is already out, the
            # sequence parks as soon as that attempt resolves.
            s.disputed = True
            if s.pending is None:
                self._park(s, "dispute")
        elif (intent.kind == "promise_to_pay" and intent.promise_day is not None
              and hasattr(self.policy, "promises")):
            self.policy.promises[reply.customer_id] = intent.promise_day
            if s.started and s.pending is None:
                s.next_action = None
                self._plan(s, now)
