"""Tests for the horizon-matched baselines.

The point of these baselines is to be a FAIR control for LearnedPolicy, so
what needs pinning is not "does it work" but "is it actually matched" --
same candidate set, same starting hour, same retry cap, same legality.
A control that quietly searches a different space proves nothing.
"""
import random

import pytest

from encore.domain import ActionKind, DeclineCode, FailedDebit, hour_of_day
from encore.policies import (
    SEARCH_HORIZON_DAYS,
    FixedSchedule,
    FixedSpread10,
    ImmediateRetry3,
    RandomInHorizon,
    cooldown_aware_start,
    legal_candidate_hours,
)
from encore.wall import SequenceState, WallConfig, decide

CFG = WallConfig()


def _failed(at_hour: int = 100) -> FailedDebit:
    # keyword args on purpose: FailedDebit orders decline BEFORE at_hour, and
    # positional construction silently swaps them into a passing-looking mess
    return FailedDebit(customer_id="cust_0001", cycle_id="cyc1", amount_paise=19900,
                       decline=DeclineCode.INSUFFICIENT_FUNDS, at_hour=at_hour)


def _state(retries: int = 0, last: int | None = None) -> SequenceState:
    return SequenceState(DeclineCode.INSUFFICIENT_FUNDS, retries, 0, last, False)


def test_learned_and_control_share_one_candidate_function():
    """model._legal_candidates must BE policies.legal_candidate_hours, not a
    copy of it -- a second implementation could drift and silently unfair the
    control this whole comparison rests on."""
    from encore import model
    assert model._legal_candidates is legal_candidate_hours


def test_every_candidate_hour_is_inside_the_execution_window():
    for h in legal_candidate_hours(100, CFG):
        hod = hour_of_day(h)
        assert hod >= CFG.window_start_hour or hod < CFG.window_end_hour


def test_candidate_horizon_is_the_documented_ten_days():
    candidates = legal_candidate_hours(100, CFG)
    assert max(candidates) < 100 + SEARCH_HORIZON_DAYS * 24
    assert min(candidates) > 100


def test_random_in_horizon_only_proposes_hours_from_the_shared_candidate_set():
    rng = random.Random(0)
    policy = RandomInHorizon(rng)
    failed, state = _failed(), _state()
    allowed = set(legal_candidate_hours(cooldown_aware_start(state, 100, CFG) - 1, CFG))
    for _ in range(200):
        action = policy.propose(failed, state, 100)
        assert action.execute_at_hour in allowed


def test_random_in_horizon_is_reproducible_under_a_seed():
    a = [RandomInHorizon(random.Random(7)).propose(_failed(), _state(), 100).execute_at_hour
         for _ in range(5)]
    b = [RandomInHorizon(random.Random(7)).propose(_failed(), _state(), 100).execute_at_hour
         for _ in range(5)]
    assert a == b


def test_random_in_horizon_respects_the_cooldown_like_the_learned_policy_does():
    """Both start their search past the cooldown, so neither wastes retry
    budget on proposals the wall will deny."""
    state = _state(retries=1, last=100)
    action = RandomInHorizon(random.Random(3)).propose(_failed(), state, 100)
    assert action.execute_at_hour >= 100 + CFG.cooldown_hours


@pytest.mark.parametrize("policy", [FixedSpread10(), RandomInHorizon(random.Random(11))])
def test_horizon_matched_policies_stop_at_the_retry_cap(policy):
    assert policy.propose(_failed(), _state(retries=CFG.max_retries_per_cycle), 100) is None


@pytest.mark.parametrize("policy", [FixedSpread10(), RandomInHorizon(random.Random(11))])
def test_horizon_matched_proposals_are_allowed_by_the_wall(policy):
    """A control that gets denied on legality would understate itself and
    flatter the learned policy -- exactly the bias this experiment removes."""
    for retries in range(CFG.max_retries_per_cycle):
        action = policy.propose(_failed(), _state(retries=retries), 100)
        assert decide(action, _state(retries=retries), CFG).allowed, action


def test_fixed_spread10_lands_on_t3_t6_t9_at_2300():
    failed = _failed(at_hour=100)
    day0 = failed.at_hour // 24
    hours = [FixedSpread10().propose(failed, _state(retries=n), 100).execute_at_hour
             for n in range(3)]
    assert hours == [(day0 + 3) * 24 + 23, (day0 + 6) * 24 + 23, (day0 + 9) * 24 + 23]


def test_fixed_spread10_reaches_further_than_fixed_t123():
    """The entire reason fixed_spread10 exists: same 3 retries, wider reach."""
    failed = _failed(at_hour=100)
    last_spread = FixedSpread10().propose(failed, _state(retries=2), 100).execute_at_hour
    last_t123 = FixedSchedule().propose(failed, _state(retries=2), 100).execute_at_hour
    assert last_spread > last_t123


def test_all_proposals_are_retries_not_nudges():
    for policy in (FixedSpread10(), RandomInHorizon(random.Random(5))):
        assert policy.propose(_failed(), _state(), 100).kind is ActionKind.RETRY


# --- horizon clamp (BROKELOG 2026-09-02) -------------------------------------
# A retry scheduled past the end of the evaluated period is unobservable, not
# successful: Portfolio.debit falls back to the live end-of-simulation balance
# when balance_history has no entry for that day, which turns every such retry
# into a near-guaranteed win no policy earned. max_hour is an EXCLUSIVE bound,
# matching range() and balance_history's 0-based day index.

def test_candidates_respect_an_exclusive_max_hour():
    bound = 100 + 5 * 24
    clamped = legal_candidate_hours(100, CFG, max_hour=bound)
    assert clamped, "clamping must not empty the candidate set at this bound"
    assert max(clamped) < bound
    assert all(h < bound for h in clamped)


def test_max_hour_only_removes_candidates_never_adds():
    """The clamp must be a pure filter over the unclamped set, so the learned
    policy and the control still search identical spaces once both are given
    the same bound."""
    bound = 100 + 5 * 24
    unclamped = legal_candidate_hours(100, CFG)
    clamped = legal_candidate_hours(100, CFG, max_hour=bound)
    assert set(clamped) <= set(unclamped)
    assert clamped == [h for h in unclamped if h < bound]


def test_default_max_hour_is_none_and_changes_nothing():
    """Backward compatibility: every number published before the clamp existed
    must stay byte-reproducible when max_hour is not supplied."""
    assert legal_candidate_hours(100, CFG) == legal_candidate_hours(100, CFG, max_hour=None)


def test_candidates_empty_rather_than_wrap_when_bound_is_already_passed():
    assert legal_candidate_hours(100, CFG, max_hour=50) == []


@pytest.mark.parametrize("policy_factory", [
    lambda bound: RandomInHorizon(random.Random(0), max_hour=bound),
    lambda bound: FixedSpread10(max_hour=bound),
    lambda bound: FixedSchedule(max_hour=bound),
    lambda bound: ImmediateRetry3(max_hour=bound),
])
def test_no_policy_proposes_past_its_max_hour(policy_factory):
    """Every stdlib policy honours the bound, not just the ones that happened
    to cross it in one regime -- fixed_spread10 and fixed_t123 both reach past
    day 30 from a late-month failure too."""
    bound = 30 * 24
    policy = policy_factory(bound)
    # a failure late in the simulated month: T+3/T+6/T+9 and the 10-day
    # random horizon all reach past the end of the world from here
    failed = _failed(at_hour=28 * 24 + 6)
    for retries in range(CFG.max_retries_per_cycle):
        action = policy.propose(failed, _state(retries=retries), failed.at_hour)
        if action is not None:
            assert action.execute_at_hour < bound, (
                f"{policy.name} proposed hour {action.execute_at_hour} "
                f"(day {action.execute_at_hour // 24}) past the bound {bound}"
            )


@pytest.mark.parametrize("policy_factory", [
    lambda: RandomInHorizon(random.Random(0)),
    lambda: FixedSpread10(),
    lambda: FixedSchedule(),
    lambda: ImmediateRetry3(),
])
def test_policies_are_unclamped_by_default(policy_factory):
    """Without max_hour the policies keep their pre-clamp behaviour exactly,
    so the clamp can never silently change a run that did not ask for it."""
    failed = _failed(at_hour=28 * 24 + 6)
    unbounded = policy_factory().propose(failed, _state(retries=2), failed.at_hour)
    assert unbounded is not None
    assert unbounded.execute_at_hour > 0


# --- promise-aware policy -------------------------------------------------------
from encore.domain import day_of_month
from encore.policies import PromiseAwarePolicy, promised_retry_hour


def _promise_policy(max_hour=720):
    return PromiseAwarePolicy(FixedSpread10(max_hour=max_hour), max_hour=max_hour)


def test_promised_retry_hour_is_2300_on_the_first_matching_day_at_or_after_start():
    h = promised_retry_hour(25, start_hour=100, max_hour=720)
    assert h == 24 * 24 + 23 and day_of_month(h) == 25
    assert promised_retry_hour(25, start_hour=24 * 24 + 23, max_hour=720) == 24 * 24 + 23
    # the next day-25 is a month away, past the evaluated window
    assert promised_retry_hour(25, start_hour=25 * 24, max_hour=720) is None


def test_promise_aware_targets_the_promised_day_when_a_promise_exists():
    policy = _promise_policy()
    policy.promises[_failed().customer_id] = 25
    action = policy.propose(_failed(), _state(), 100)
    assert day_of_month(action.execute_at_hour) == 25 and action.execute_at_hour % 24 == 23
    assert decide(action, _state(), CFG).allowed


def test_promise_aware_equals_fallback_without_a_promise():
    policy = _promise_policy()
    assert policy.propose(_failed(), _state(), 100) == FixedSpread10(max_hour=720).propose(
        _failed(), _state(), 100)


def test_promise_aware_falls_back_when_the_promised_day_is_past_the_window():
    policy = _promise_policy(max_hour=200)
    policy.promises[_failed().customer_id] = 25
    assert policy.propose(_failed(), _state(), 100) == FixedSpread10(max_hour=200).propose(
        _failed(), _state(), 100)


def test_promise_aware_never_proposes_before_the_cooldown_after_a_miss():
    policy = _promise_policy()
    policy.promises[_failed().customer_id] = 25
    missed_at = 24 * 24 + 23
    state = _state(retries=1, last=missed_at)
    action = policy.propose(_failed(), state, missed_at)
    assert action is not None and action.execute_at_hour >= missed_at + CFG.cooldown_hours
    assert decide(action, state, CFG).allowed


def test_promise_aware_stops_at_the_retry_cap():
    policy = _promise_policy()
    policy.promises[_failed().customer_id] = 25
    assert policy.propose(_failed(), _state(retries=CFG.max_retries_per_cycle), 100) is None
