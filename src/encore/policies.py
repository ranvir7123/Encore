import random
from typing import Protocol

from encore.domain import (
    DAYS_PER_MONTH,
    HOURS_PER_DAY,
    ActionKind,
    FailedDebit,
    ProposedAction,
    day_of_month,
    hour_of_day,
)
from encore.wall import SequenceState, WallConfig

# LearnedPolicy scans this many days of candidate retry hours per attempt.
# The horizon-matched baselines below deliberately reuse the same number --
# that equality is the whole point of the control, so it lives in one place.
SEARCH_HORIZON_DAYS = 10


def legal_candidate_hours(failure_hour: int, cfg: WallConfig,
                          horizon_days: int = SEARCH_HORIZON_DAYS,
                          max_hour: int | None = None) -> list[int]:
    """Every hour within `horizon_days` after failure_hour that falls inside
    the wall's execution window, and strictly before `max_hour` if given.

    `max_hour` is the exclusive end of the evaluated period (BROKELOG
    2026-09-02). Without it a late-month failure can be retried past the end
    of the simulated world, where `Portfolio.debit` finds no `balance_history`
    entry for that day and falls back to the live end-of-simulation balance --
    which is post-salary-credit and clears almost every amount. Those retries
    are unobservable, not successful, and they landed disproportionately on
    the uniform control that the refutation in entries 9-10 depends on.
    It is a pure filter over the unclamped set, so a learned policy and a
    control given the same bound still search identical spaces.

    Moved here from model.py (where it was `_legal_candidates`) so the
    horizon-matched baselines can search the IDENTICAL candidate set
    LearnedPolicy searches, from a module importing no third-party packages.
    A second copy of this logic would silently break the very control it
    exists to provide, and would also drag scikit-learn into policies.py.
    """
    horizon = range(failure_hour + 1, failure_hour + horizon_days * HOURS_PER_DAY)
    return [h for h in horizon
            if (max_hour is None or h < max_hour)
            and (cfg.window_start_hour <= hour_of_day(h) or hour_of_day(h) < cfg.window_end_hour)]


def cooldown_aware_start(state: SequenceState, now_hour: int, cfg: WallConfig) -> int:
    """First hour a retry could legally land, given the wall's cooldown.

    Extracted from LearnedPolicy so a horizon-matched control starts its
    search at exactly the same hour. Without this, a "random" baseline would
    also be handicapped by proposing inside the cooldown and burning retry
    budget on denials -- which would flatter the learned policy for a reason
    that has nothing to do with learning.
    """
    if state.last_attempt_hour is None:
        return now_hour + 1
    return max(now_hour + 1, state.last_attempt_hour + cfg.cooldown_hours)


class Policy(Protocol):
    name: str

    def propose(self, failed: FailedDebit, state: SequenceState,
                now_hour: int) -> ProposedAction | None: ...


class ImmediateRetry3:
    """Deliberately dumb baseline: retry an hour after each failure, 3 times."""
    name = "immediate_x3"

    def __init__(self, max_hour: int | None = None) -> None:
        self.max_hour = max_hour

    def propose(self, failed, state, now_hour):
        if state.retries_attempted >= 3:
            return None
        at_hour = now_hour + 1
        if self.max_hour is not None and at_hour >= self.max_hour:
            return None
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, at_hour, state.retries_attempted + 1)


class FixedSchedule:
    """Razorpay's documented subscription auto-retry shape: T+1, T+2, T+3 at 23:00."""
    name = "fixed_t123"

    def __init__(self, max_hour: int | None = None) -> None:
        self.max_hour = max_hour

    def propose(self, failed, state, now_hour):
        n = state.retries_attempted
        if n >= 3:
            return None
        target_day = (failed.at_hour // HOURS_PER_DAY) + (n + 1)
        at_hour = target_day * HOURS_PER_DAY + 23
        if self.max_hour is not None and at_hour >= self.max_hour:
            return None
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, at_hour, n + 1)


class FixedSpread10:
    """Practical horizon-matched baseline: the same 10-day reach LearnedPolicy
    has, spent dumbly -- T+3, T+6, T+9 at 23:00 (23:00 is inside the wall's
    22:00-07:00 execution window, and the 3-day spacing clears the 24h
    cooldown by construction).

    Answers: does the learned policy beat a sensible heuristic that simply
    reaches as far into the month as it does? Contrast with FixedSchedule,
    whose T+1/T+2/T+3 can only ever see the three days after the failure.
    """
    name = "fixed_spread10"

    def __init__(self, cfg: WallConfig | None = None, max_hour: int | None = None) -> None:
        self._cfg = cfg or WallConfig()
        self.max_hour = max_hour

    def propose(self, failed, state, now_hour):
        n = state.retries_attempted
        if n >= self._cfg.max_retries_per_cycle:
            return None
        target_day = (failed.at_hour // HOURS_PER_DAY) + 3 * (n + 1)
        at_hour = target_day * HOURS_PER_DAY + 23
        if self.max_hour is not None and at_hour >= self.max_hour:
            return None
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, at_hour, n + 1)


class RandomInHorizon:
    """Horizon-matched SCIENTIFIC control: identical candidate set and
    identical cooldown-aware start to LearnedPolicy, but the hour is drawn
    uniformly at random instead of ranked by the model.

    This is the baseline that isolates the one thing in question -- whether
    the model's *ranking* beats chance -- from the width of the window it
    ranks over. If encore_learned beats fixed_t123 but merely ties this, the
    win was reach, not timing intelligence.

    rng is injected, never constructed internally (CLAUDE.md: all randomness
    from seeded random.Random instances passed explicitly).
    """
    name = "random_in_horizon"

    def __init__(self, rng: random.Random, cfg: WallConfig | None = None,
                 max_hour: int | None = None) -> None:
        self.rng = rng
        self._cfg = cfg or WallConfig()
        self.max_hour = max_hour

    def propose(self, failed, state, now_hour):
        if state.retries_attempted >= self._cfg.max_retries_per_cycle:
            return None
        start = cooldown_aware_start(state, now_hour, self._cfg)
        candidates = legal_candidate_hours(start - 1, self._cfg, max_hour=self.max_hour)
        if not candidates:
            return None
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, self.rng.choice(candidates),
                              state.retries_attempted + 1)


def promised_retry_hour(day: int, start_hour: int, max_hour: int | None) -> int | None:
    """23:00 on the first calendar day at or after start_hour whose day-of-month
    is `day`, or None if no such hour exists strictly before max_hour. 23:00 is
    inside the wall's 22:00-07:00 window and after that day's salary credit,
    which the simulator posts at hour 0 of the day."""
    d = start_hour // HOURS_PER_DAY
    last_day = (max_hour // HOURS_PER_DAY) if max_hour is not None else d + DAYS_PER_MONTH
    while d < last_day:
        h = d * HOURS_PER_DAY + 23
        if h >= start_hour and day_of_month(h) == day and (max_hour is None or h < max_hour):
            return h
        d += 1
    return None


class PromiseAwarePolicy:
    """Retries on the day the customer said money arrives; otherwise defers to
    a deterministic fallback.

    The promise comes from the reply parser (a pydantic ReplyIntent), which is
    the only place a language model can ever influence timing -- and it still
    never touches legality: every proposal goes through wall.decide() like any
    other. `promises` is per-run state set by whoever parsed the replies
    (evaluate.run_matrix per seed, agent.RecoveryAgent as replies arrive), so
    the Policy protocol and the other policies stay untouched.
    """
    name = "promise_aware"

    def __init__(self, fallback: Policy, cfg: WallConfig | None = None,
                 max_hour: int | None = None) -> None:
        self.fallback = fallback
        self._cfg = cfg or WallConfig()
        self.max_hour = max_hour
        self.promises: dict[str, int] = {}

    def propose(self, failed, state, now_hour):
        if state.retries_attempted >= self._cfg.max_retries_per_cycle:
            return None
        start = cooldown_aware_start(state, now_hour, self._cfg)
        day = self.promises.get(failed.customer_id)
        if day is not None:
            h = promised_retry_hour(day, start, self.max_hour)
            if h is not None:
                return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                                      failed.amount_paise, h, state.retries_attempted + 1)
        action = self.fallback.propose(failed, state, now_hour)
        if action is None or action.execute_at_hour >= start:
            return action
        # The fallback's failure-anchored schedule has already passed -- a missed
        # promise consumed that slot. Re-anchor to the cooldown start at 23:00
        # so no retry budget is burnt on a proposal the wall would deny as
        # cooldown_active. Still clamped to the evaluated window.
        h = (start // HOURS_PER_DAY) * HOURS_PER_DAY + 23
        if h < start:
            h += HOURS_PER_DAY
        if self.max_hour is not None and h >= self.max_hour:
            return None
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, h, state.retries_attempted + 1)
