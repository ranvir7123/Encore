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
    assert decide(retry(1, IN_WINDOW), state(killed=True), CFG) == Decision(False, "sequence_killed")
    assert decide(nudge(IN_WINDOW), state(killed=True), CFG) == Decision(False, "sequence_killed")


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
    assert decide(retry(1, 23), state(), CFG) == Decision(True, "ok")              # 23:00 ok
    assert decide(retry(1, 24 + 6), state(), CFG) == Decision(True, "ok")          # 06:00 next day ok
    assert decide(retry(1, 24 + 8), state(), CFG) == Decision(False, "outside_execution_window")  # 08:00 denied


def test_nudge_budget_exhausted():
    d = decide(nudge(IN_WINDOW), state(nudges_sent=2), CFG)
    assert d == Decision(False, "nudge_budget_exhausted")


def test_nudges_ignore_execution_window_but_respect_kill_and_budget():
    # A payment-link nudge is a message, not a debit — windows govern debits only.
    assert decide(nudge(12), state(), CFG) == Decision(True, "ok")


def test_kill_beats_cap_beats_cooldown_precedence():
    s = state(killed=True, retries_attempted=3, last_attempt_hour=IN_WINDOW)
    assert decide(retry(4, IN_WINDOW + 1), s, CFG) == Decision(False, "sequence_killed")


# Precedence-conflict tests: genuine simultaneous rule violations.
# These pin the exact conflict resolution order: killed > hard_decline > cap > cooldown > window > budget.


def test_precedence_killed_beats_hard_decline():
    """Killed takes precedence even when hard decline applies."""
    s = state(killed=True, original_decline=DeclineCode.MANDATE_REVOKED)
    assert decide(retry(1, IN_WINDOW), s, CFG) == Decision(False, "sequence_killed")


def test_precedence_killed_beats_window():
    """Killed takes precedence even when outside execution window."""
    s = state(killed=True)
    assert decide(retry(1, 12), s, CFG) == Decision(False, "sequence_killed")


def test_precedence_killed_beats_budget_on_nudge():
    """Killed takes precedence even when nudge budget exhausted."""
    s = state(killed=True, nudges_sent=2)
    assert decide(nudge(IN_WINDOW), s, CFG) == Decision(False, "sequence_killed")


def test_precedence_hard_decline_beats_cap():
    """Hard decline takes precedence even when retry cap exceeded."""
    s = state(original_decline=DeclineCode.ACCOUNT_CLOSED, retries_attempted=3)
    assert decide(retry(4, IN_WINDOW), s, CFG) == Decision(False, "hard_decline_terminal")


def test_precedence_hard_decline_beats_cooldown():
    """Hard decline takes precedence even when in cooldown period."""
    s = state(original_decline=DeclineCode.RISK_DECLINED, retries_attempted=1, last_attempt_hour=23)
    assert decide(retry(2, 30), s, CFG) == Decision(False, "hard_decline_terminal")


def test_precedence_hard_decline_beats_window():
    """Hard decline takes precedence even when outside execution window."""
    s = state(original_decline=DeclineCode.MANDATE_REVOKED)
    assert decide(retry(1, 12), s, CFG) == Decision(False, "hard_decline_terminal")


def test_precedence_cap_beats_cooldown():
    """Retry cap takes precedence over cooldown check."""
    s = state(retries_attempted=3, last_attempt_hour=23)
    assert decide(retry(4, 30), s, CFG) == Decision(False, "retry_cap_exceeded")


def test_precedence_cap_beats_window():
    """Retry cap takes precedence over execution window check."""
    s = state(retries_attempted=3)
    assert decide(retry(4, 12), s, CFG) == Decision(False, "retry_cap_exceeded")


def test_precedence_cooldown_beats_window():
    """Cooldown takes precedence over execution window check.

    Example: retry at hour 36 (noon, outside window) with last_attempt_hour=23.
    Δ = 13 hours < 24 hours cooldown → cooldown_active, not outside_execution_window.
    """
    s = state(retries_attempted=1, last_attempt_hour=23)
    assert decide(retry(2, 36), s, CFG) == Decision(False, "cooldown_active")


# Cooldown boundary tests


def test_cooldown_boundary_exactly_24_hours_allowed():
    """Cooldown at exact boundary (Δ == cooldown_hours) is allowed (inclusive).

    This documents the implementation's choice: >= cooldown_hours (not strictly >).
    """
    s = state(retries_attempted=1, last_attempt_hour=23)
    # hour 23 + 24 = hour 47 (day 2, hour 23:00)
    assert decide(retry(2, 47), s, CFG) == Decision(True, "ok")


def test_cooldown_negative_delta_blocked():
    """Execute hour < last attempt hour → cooldown_active (safe-by-default).

    Pins behavior for wrapped or backwards-in-time clock readings.
    """
    s = state(retries_attempted=1, last_attempt_hour=30)
    # Attempting to retry at hour 20 (day 1) after last attempt at hour 30 (day 2)
    assert decide(retry(2, 20), s, CFG) == Decision(False, "cooldown_active")


# Nudge-vs-hard-decline behavior


def test_nudge_with_hard_decline_allowed_if_budget_available():
    """NPCI debit rules govern debits; nudges are contact messages gated only by kill switch and budget.

    A hard decline stops retries (debits) immediately but permits sending payment links (nudges).
    This test pins that behavior: nudge on a hard-declined sequence is allowed if killed=False
    and nudges_sent < max_nudges_per_cycle. The kill switch is the only way to stop all contact.
    """
    s = state(original_decline=DeclineCode.MANDATE_REVOKED, killed=False, nudges_sent=0)
    assert decide(nudge(IN_WINDOW), s, CFG) == Decision(True, "ok")
