from dataclasses import dataclass

from encore.domain import HARD_DECLINES, ActionKind, DeclineCode, ProposedAction, hour_of_day


@dataclass(frozen=True)
class WallConfig:
    # NPCI (Aug 2025): one original execution + max 3 retries, in non-peak windows.
    # https://www.npci.org.in/ (circular referenced in README sources)
    max_retries_per_cycle: int = 3
    cooldown_hours: int = 24
    window_start_hour: int = 22  # debits allowed 22:00-07:00
    window_end_hour: int = 7
    max_nudges_per_cycle: int = 2


@dataclass(frozen=True)
class SequenceState:
    original_decline: DeclineCode
    retries_attempted: int
    nudges_sent: int
    last_attempt_hour: int | None
    killed: bool


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


def _in_window(h: int, cfg: WallConfig) -> bool:
    hod = hour_of_day(h)
    if cfg.window_start_hour <= cfg.window_end_hour:
        return cfg.window_start_hour <= hod < cfg.window_end_hour
    return hod >= cfg.window_start_hour or hod < cfg.window_end_hour


def decide(action: ProposedAction, state: SequenceState, cfg: WallConfig) -> Decision:
    if state.killed:
        return Decision(False, "sequence_killed")
    if action.kind is ActionKind.RETRY:
        if state.original_decline in HARD_DECLINES:
            return Decision(False, "hard_decline_terminal")
        if state.retries_attempted >= cfg.max_retries_per_cycle:
            return Decision(False, "retry_cap_exceeded")
        if (state.last_attempt_hour is not None
                and action.execute_at_hour - state.last_attempt_hour < cfg.cooldown_hours):
            return Decision(False, "cooldown_active")
        if not _in_window(action.execute_at_hour, cfg):
            return Decision(False, "outside_execution_window")
        return Decision(True, "ok")
    if state.nudges_sent >= cfg.max_nudges_per_cycle:
        return Decision(False, "nudge_budget_exhausted")
    return Decision(True, "ok")
