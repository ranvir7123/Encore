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
