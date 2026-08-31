from encore.domain import (
    HARD_DECLINES,
    ActionKind,
    DeclineCode,
    ProposedAction,
    attempt_id,
    day_of_month,
    hour_of_day,
)


def test_hard_declines_are_the_documented_set():
    assert HARD_DECLINES == {
        DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED, DeclineCode.RISK_DECLINED,
    }


def test_attempt_id_is_deterministic_and_unique_per_attempt():
    a1 = ProposedAction(ActionKind.RETRY, "c1", "2026-09", 49900, 100, 1)
    a1b = ProposedAction(ActionKind.RETRY, "c1", "2026-09", 49900, 100, 1)
    a2 = ProposedAction(ActionKind.RETRY, "c1", "2026-09", 49900, 200, 2)
    assert attempt_id(a1) == attempt_id(a1b)
    assert attempt_id(a1) != attempt_id(a2)


def test_time_helpers():
    assert hour_of_day(25) == 1
    assert day_of_month(0) == 1
    assert day_of_month(24 * 29) == 30
    assert day_of_month(24 * 30) == 1  # wraps into next 30-day month
