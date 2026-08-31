from typing import Protocol

from encore.domain import HOURS_PER_DAY, ActionKind, FailedDebit, ProposedAction
from encore.wall import SequenceState


class Policy(Protocol):
    name: str

    def propose(self, failed: FailedDebit, state: SequenceState,
                now_hour: int) -> ProposedAction | None: ...


class ImmediateRetry3:
    """Deliberately dumb baseline: retry an hour after each failure, 3 times."""
    name = "immediate_x3"

    def propose(self, failed, state, now_hour):
        if state.retries_attempted >= 3:
            return None
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, now_hour + 1, state.retries_attempted + 1)


class FixedSchedule:
    """Razorpay's documented subscription auto-retry shape: T+1, T+2, T+3 at 23:00."""
    name = "fixed_t123"

    def propose(self, failed, state, now_hour):
        n = state.retries_attempted
        if n >= 3:
            return None
        target_day = (failed.at_hour // HOURS_PER_DAY) + (n + 1)
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, target_day * HOURS_PER_DAY + 23, n + 1)
