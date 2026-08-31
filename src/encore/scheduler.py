from dataclasses import dataclass, field

from encore.audit import AttemptLedger, AuditLog
from encore.domain import ActionKind, FailedDebit, ProposedAction, attempt_id
from encore.policies import Policy
from encore.simulator import Portfolio
from encore.wall import Decision, SequenceState, WallConfig, decide


class SimulatedRail:
    def __init__(self, portfolio: Portfolio) -> None:
        self._p = portfolio

    def execute(self, action: ProposedAction) -> bool:
        return self._p.debit(action.customer_id, action.execute_at_hour) is None


@dataclass
class RunResult:
    recovered_paise: int = 0
    attempts_executed: int = 0
    attempts_denied: int = 0
    nudges_sent: int = 0
    parked: int = 0
    denials_by_reason: dict[str, int] = field(default_factory=dict)


class Scheduler:
    def __init__(self, wall_cfg: WallConfig) -> None:
        self.wall_cfg = wall_cfg

    def run(self, portfolio: Portfolio, failures: list[FailedDebit], policy: Policy,
            rail, audit: AuditLog, ledger: AttemptLedger,
            killed_customers: set[str] | None = None) -> RunResult:
        result = RunResult()
        killed = killed_customers or set()
        for failed in failures:
            state = SequenceState(failed.decline, 0, 0, None, failed.customer_id in killed)
            while True:
                action = policy.propose(failed, state, state.last_attempt_hour or failed.at_hour)
                if action is None:
                    result.parked += 1
                    audit.append({"event": "park", "customer_id": failed.customer_id,
                                  "cycle_id": failed.cycle_id, "policy": policy.name})
                    break
                decision: Decision = decide(action, state, self.wall_cfg)
                audit.append({"event": "decision", "customer_id": action.customer_id,
                              "attempt_id": attempt_id(action), "kind": str(action.kind),
                              "at_hour": action.execute_at_hour, "allowed": decision.allowed,
                              "reason": decision.reason, "policy": policy.name})
                if not decision.allowed:
                    result.attempts_denied += 1
                    result.denials_by_reason[decision.reason] = (
                        result.denials_by_reason.get(decision.reason, 0) + 1)
                    if decision.reason in ("hard_decline_terminal", "sequence_killed",
                                           "retry_cap_exceeded"):
                        break  # terminal denials end the sequence
                    state = SequenceState(state.original_decline, state.retries_attempted + 1,
                                          state.nudges_sent, action.execute_at_hour, state.killed)
                    continue
                aid = attempt_id(action)
                if ledger.already_executed(aid):
                    audit.append({"event": "duplicate_blocked", "attempt_id": aid})
                    break
                ledger.record(aid)
                if action.kind is ActionKind.NUDGE:
                    result.nudges_sent += 1
                    state = SequenceState(state.original_decline, state.retries_attempted,
                                          state.nudges_sent + 1, state.last_attempt_hour,
                                          state.killed)
                    audit.append({"event": "nudge", "customer_id": action.customer_id,
                                  "attempt_id": aid})
                    continue
                success = rail.execute(action)
                result.attempts_executed += 1
                audit.append({"event": "execution", "customer_id": action.customer_id,
                              "attempt_id": aid, "at_hour": action.execute_at_hour,
                              "outcome": "success" if success else "failure",
                              "amount_paise": action.amount_paise, "policy": policy.name,
                              "original_decline": str(state.original_decline),
                              "attempt_no": action.attempt_no})
                if success:
                    result.recovered_paise += action.amount_paise
                    break
                state = SequenceState(state.original_decline, state.retries_attempted + 1,
                                      state.nudges_sent, action.execute_at_hour, state.killed)
        return result
