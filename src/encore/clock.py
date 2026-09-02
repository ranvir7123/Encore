"""The agent's sense of time, injected so wall.py stays clock-free (CLAUDE.md:
no I/O, no clocks, no randomness in the wall)."""
import time
from typing import Protocol


class Clock(Protocol):
    hour: int

    def advance_to(self, sim_hour: int) -> None: ...

    def monotonic(self) -> float: ...


class InstantClock:
    """Tests: no sleeping; monotonic() advances one fake second per call so
    real-time timeouts are deterministic."""

    def __init__(self) -> None:
        self.hour = 0
        self._t = 0.0

    def advance_to(self, sim_hour: int) -> None:
        self.hour = max(self.hour, sim_hour)

    def monotonic(self) -> float:
        self._t += 1.0
        return self._t


class SimClock:
    """Demo: each simulated hour costs seconds_per_sim_hour of wall-clock time."""

    def __init__(self, seconds_per_sim_hour: float, sleep=time.sleep,
                 monotonic=time.monotonic) -> None:
        self.hour = 0
        self._spsh, self._sleep, self._monotonic = seconds_per_sim_hour, sleep, monotonic

    def advance_to(self, sim_hour: int) -> None:
        if sim_hour > self.hour:
            self._sleep((sim_hour - self.hour) * self._spsh)
            self.hour = sim_hour

    def monotonic(self) -> float:
        return self._monotonic()
