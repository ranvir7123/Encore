import pytest

from encore.domain import ActionKind, DeclineCode, ProposedAction
from encore.wall import Decision, SequenceState, WallConfig, decide

CFG = WallConfig()


def retry(attempt_no: int, at_hour: int) -> ProposedAction:
    return ProposedAction(ActionKind.RETRY, "c1", "2026-09", 49900, at_hour, attempt_no)


def nudge(at_hour: int) -> ProposedAction:
    return ProposedAction(ActionKind.NUDGE, "c1", "2026-09", 49900, at_hour, 1)


def state(**kw) -> SequenceState:
    base = {
        "original_decline": DeclineCode.INSUFFICIENT_FUNDS,
        "retries_attempted": 0,
        "nudges_sent": 0,
        "last_attempt_hour": None,
        "killed": False,
    }
    base.update(kw)
    return SequenceState(**base)


IN_WINDOW = 23  # 23:00 on day 1 — inside the 22:00-07:00 non-peak window


def test_happy_path_first_retry_in_window_is_allowed():
    assert decide(retry(1, IN_WINDOW), state(), CFG) == Decision(True, "ok")


@pytest.mark.parametrize("code", [
    DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED, DeclineCode.RISK_DECLINED,
])
def test_hard_declines_are_terminal_no_retry_ever(code):
    d = decide(retry(1, IN_WINDOW), state(original_decline=code), CFG)
    assert d == Decision(False, "hard_decline_terminal")


def test_killed_sequence_refuses_everything_even_nudges():
    assert decide(retry(1, IN_WINDOW), state(killed=True), CFG).reason == "sequence_killed"
    assert decide(nudge(IN_WINDOW), state(killed=True), CFG).reason == "sequence_killed"


def test_fourth_retry_is_denied_npci_cap():
    d = decide(retry(4, IN_WINDOW), state(retries_attempted=3), CFG)
    assert d == Decision(False, "retry_cap_exceeded")


def test_cooldown_blocks_back_to_back_retries():
    d = decide(retry(2, 30), state(retries_attempted=1, last_attempt_hour=23), CFG)
    assert d == Decision(False, "cooldown_active")  # only 7h since last attempt


def test_peak_hours_execution_is_denied():
    noon = 12
    d = decide(retry(1, noon), state(), CFG)
    assert d == Decision(False, "outside_execution_window")


def test_window_wraps_midnight_correctly():
    assert decide(retry(1, 23), state(), CFG).allowed          # 23:00 ok
    assert decide(retry(1, 24 + 6), state(), CFG).allowed      # 06:00 next day ok
    assert not decide(retry(1, 24 + 8), state(), CFG).allowed  # 08:00 denied


def test_nudge_budget_exhausted():
    d = decide(nudge(IN_WINDOW), state(nudges_sent=2), CFG)
    assert d == Decision(False, "nudge_budget_exhausted")


def test_nudges_ignore_execution_window_but_respect_kill_and_budget():
    # A payment-link nudge is a message, not a debit — windows govern debits only.
    assert decide(nudge(12), state(), CFG).allowed


def test_kill_beats_cap_beats_cooldown_precedence():
    s = state(killed=True, retries_attempted=3, last_attempt_hour=IN_WINDOW)
    assert decide(retry(4, IN_WINDOW + 1), s, CFG).reason == "sequence_killed"
