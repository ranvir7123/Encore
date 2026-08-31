# Encore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A failed-debit retry sequencer for subscription payments: a hard-coded compliance wall around a learned retry-timing policy, measured in rupees recovered per 1,000 failed debits against dumb baselines on a regime-shifted held-out portfolio, executing a demo slice on real Razorpay test-mode APIs.

**Architecture:** A CLI-first pure-Python pipeline. A seeded portfolio simulator emits failed-debit events with ground truth; policies *propose* actions; a pure-function compliance wall *disposes* (allow/deny with reason codes); an idempotent scheduler executes allowed actions through a `PaymentRail` interface (simulated oracle by default, real Razorpay Payment Links + polling for the demo slice); everything lands in an append-only JSONL audit log that the metrics and HTML scoreboard are computed from. The LLM appears in exactly one place — parsing customer free-text replies into a validated schema — and holds zero authority over money.

**Tech Stack:** Python 3.13, uv (locked deps), scikit-learn (`HistGradientBoostingClassifier`), pydantic v2 (parser I/O validation only), httpx (Razorpay REST), anthropic SDK (reply parser), pytest + ruff, GitHub Actions CI. No web framework; the report is generated static HTML.

## Global Constraints

- All money amounts are **integer paise**. A `float` touching an amount is a bug.
- The compliance wall (`wall.py`) is **pure functions**: no I/O, no clock reads, no randomness. Time comes in as an argument.
- **No LLM call may exist on the money path.** The parser output is validated by pydantic and then judged by the wall like any other input.
- Every executed or denied action appends one line to the audit log with a machine-readable reason code.
- All randomness flows from an explicit `seed` argument. `random.Random(seed)` instances only — never the global `random` module, never `datetime.now()` inside simulation code.
- Windows dev machine: no POSIX-only calls; paths via `pathlib`.
- Repo is **public from commit #1**: every commit message is written knowing a judge may read it. No secrets in git — keys live in `.env` (gitignored), loaded via `os.environ`.
- Broke-log discipline (see `CLAUDE.md` task): unexpected failures get a dated `BROKELOG.md` entry before the fix is committed.
- NPCI/Razorpay rule citations live as comments **on the constants they constrain**, with URLs.
- Package layout: `src/encore/`; run everything as `uv run encore <command>` or `uv run pytest`.

---

## Prerequisites (user actions — Claude cannot do these)

1. **Razorpay account:** sign up at razorpay.com (skip KYC), switch the dashboard toggle to **Test Mode**, generate keys (Settings → API Keys). Put `RAZORPAY_KEY_ID` (`rzp_test_...`) and `RAZORPAY_KEY_SECRET` in `C:\dev\encore\.env`.
2. **Anthropic API key** with a few dollars of credit → `ANTHROPIC_API_KEY` in `.env`. (Everything except the live-LLM parser comparison works without it.)
3. **GitHub repo:** create public repo `encore` under your account (empty, no README). Have `git` configured with your name/email.

---

### Task 1: Scaffold, tooling, broke-log system

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `CLAUDE.md`, `BROKELOG.md`, `README.md` (stub), `src/encore/__init__.py`, `tests/__init__.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: the `encore` package importable via `uv run python -c "import encore"`; `uv run pytest` and `uv run ruff check .` green; CI running both on push.

- [ ] **Step 1: Initialize project**

```bash
cd C:\dev\encore
git init -b main
uv init --name encore --package --python 3.13
uv add scikit-learn pydantic httpx anthropic python-dotenv
uv add --dev pytest ruff
```

- [ ] **Step 2: Write `pyproject.toml` script entry and ruff config** (merge into the generated file)

```toml
[project.scripts]
encore = "encore.cli:main"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `.gitignore` and `.env.example`**

```gitignore
.env
.venv/
__pycache__/
*.pyc
runs/
dist/
```

```bash
# .env.example — copy to .env and fill in
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
```

- [ ] **Step 4: Write `CLAUDE.md`** (the broke-log enforcement lives here — this is what makes failure tracking semi-automatic when building with Claude Code)

```markdown
# Encore — project rules

## Broke-log (non-negotiable)
Whenever ANY of these happen, append an entry to BROKELOG.md BEFORE fixing:
- a test fails for a reason you did not predict
- a bug is found in code that was believed done
- a design decision is reversed
- an external API behaves differently than documented

Entry format (append at the bottom):
### <ISO date> — <one-line title>
- **What happened:** <observed behavior, verbatim error if any>
- **Evidence:** <command + output snippet, or failing test name>
- **Root cause:** <fill after diagnosis>
- **Fix:** <commit hash after fixing>
- **Still open:** <anything unresolved, or "nothing">

Never delete or edit past entries. The buildathon essay is assembled from this file.

## Engineering rules
- Money is integer paise everywhere. Floats near money = bug.
- wall.py stays pure: no I/O, no clocks, no randomness. If you need one, pass it in.
- No LLM call on the money path. Parser output goes through pydantic, then the wall.
- All randomness from seeded random.Random instances passed explicitly.
- Every public repo commit message is written for a judge's eyes.
- Run `uv run pytest -q` and `uv run ruff check .` before every commit.

## Verification
Never claim something works without showing the command and its real output.
```

- [ ] **Step 5: Write `BROKELOG.md`**

```markdown
# Broke-log

Append-only record of what broke while building Encore. Read
[CLAUDE.md](CLAUDE.md) for the entry rules. The "what broke and how you got
out" submission answer is assembled from this file — entries are never
edited after the fact.
```

- [ ] **Step 6: Write CI** — `.github/workflows/ci.yml`

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run pytest -q
```

- [ ] **Step 7: Verify everything runs**

Run: `uv run pytest -q` → expected: `no tests ran` (exit 5 is fine at this point)
Run: `uv run ruff check .` → expected: `All checks passed!`

- [ ] **Step 8: First commit and push**

```bash
git add -A
git commit -m "chore: scaffold encore — uv project, CI, broke-log system"
git remote add origin https://github.com/<USER>/encore.git
git push -u origin main
```

---

### Task 2: Razorpay test-mode spike

Do this before building anything on assumptions. The research says Payment Links + polling work in test mode without feature flags — verify it, and record what's actually true.

**Files:**
- Create: `src/encore/razorpay_client.py`, `scripts/spike.py`, `docs/spike-notes.md`

**Interfaces:**
- Produces: `RazorpayClient` with `create_payment_link(amount_paise: int, description: str, reference_id: str) -> dict` and `fetch_payment_link(link_id: str) -> dict`, using httpx with basic auth from env. Task 10 reuses this client.

- [ ] **Step 1: Write the client**

```python
# src/encore/razorpay_client.py
import os
import httpx

BASE = "https://api.razorpay.com/v1"


class RazorpayClient:
    def __init__(self) -> None:
        auth = (os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"])
        self._http = httpx.Client(base_url=BASE, auth=auth, timeout=20.0)

    def create_payment_link(self, amount_paise: int, description: str, reference_id: str) -> dict:
        resp = self._http.post("/payment_links", json={
            "amount": amount_paise,
            "currency": "INR",
            "description": description,
            "reference_id": reference_id,
        })
        resp.raise_for_status()
        return resp.json()

    def fetch_payment_link(self, link_id: str) -> dict:
        resp = self._http.get(f"/payment_links/{link_id}")
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 2: Write the spike script**

```python
# scripts/spike.py — verify what test mode actually permits. Run once, record output.
from dotenv import load_dotenv

load_dotenv()
from encore.razorpay_client import RazorpayClient  # noqa: E402

c = RazorpayClient()
link = c.create_payment_link(50000, "Encore spike: can we create links?", "spike-001")
print("created:", link["id"], link["status"], link["short_url"])
print("fetched:", c.fetch_payment_link(link["id"])["status"])
```

- [ ] **Step 3: Run it and record reality**

Run: `uv run python scripts/spike.py`
Expected: a link id + status `created` + a short URL you can open in a browser.

Then, manually: open the short URL, pay once with UPI id `success@razorpay`, re-run the fetch, confirm status moves to `paid`. Try `failure@razorpay` on a second link. Write everything observed — including anything that contradicts this plan — into `docs/spike-notes.md`. If anything surprised you, that's the first BROKELOG entry.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: razorpay client + test-mode spike notes"
```

---

### Task 3: Domain types and decline taxonomy

**Files:**
- Create: `src/encore/domain.py`, `tests/test_domain.py`

**Interfaces:**
- Produces (used by every later task):
  - `DeclineCode` enum, `HARD_DECLINES: frozenset[DeclineCode]`
  - `FailedDebit(customer_id: str, cycle_id: str, amount_paise: int, decline: DeclineCode, at_hour: int)` frozen dataclass
  - `ActionKind` enum (`RETRY`, `NUDGE`), `ProposedAction(kind, customer_id, cycle_id, amount_paise, execute_at_hour, attempt_no)` frozen dataclass
  - `attempt_id(action) -> str` deterministic id function
  - Simulated time is **hours since portfolio start** (`int`); `hour_of_day(h) -> int`, `day_of_month(h, start_day: int = 1) -> int` helpers assuming 30-day months (documented simplification).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_domain.py
from encore.domain import (
    HARD_DECLINES, ActionKind, DeclineCode, ProposedAction,
    attempt_id, day_of_month, hour_of_day,
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
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_domain.py -q` → FAIL (module missing)

- [ ] **Step 3: Implement**

```python
# src/encore/domain.py
from dataclasses import dataclass
from enum import StrEnum


class DeclineCode(StrEnum):
    # Soft declines: retry can help. Modeled on Razorpay's documented payment
    # failure reasons (https://razorpay.com/docs/payments/payments/failed-payments/).
    INSUFFICIENT_FUNDS = "insufficient_funds"
    ISSUER_DOWN = "issuer_down"
    GATEWAY_TIMEOUT = "gateway_timeout"
    # Hard declines: retrying is a compliance violation, not an optimization.
    MANDATE_REVOKED = "mandate_revoked"
    ACCOUNT_CLOSED = "account_closed"
    RISK_DECLINED = "risk_declined"


HARD_DECLINES = frozenset({
    DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED, DeclineCode.RISK_DECLINED,
})


class ActionKind(StrEnum):
    RETRY = "retry"
    NUDGE = "nudge"


@dataclass(frozen=True)
class FailedDebit:
    customer_id: str
    cycle_id: str
    amount_paise: int
    decline: DeclineCode
    at_hour: int


@dataclass(frozen=True)
class ProposedAction:
    kind: ActionKind
    customer_id: str
    cycle_id: str
    amount_paise: int
    execute_at_hour: int
    attempt_no: int


def attempt_id(action: ProposedAction) -> str:
    return f"{action.customer_id}:{action.cycle_id}:{action.kind}:{action.attempt_no}"


HOURS_PER_DAY = 24
DAYS_PER_MONTH = 30  # simulation simplification, stated in README


def hour_of_day(h: int) -> int:
    return h % HOURS_PER_DAY


def day_of_month(h: int) -> int:
    return (h // HOURS_PER_DAY) % DAYS_PER_MONTH + 1
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_domain.py -q` → PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: domain types, decline taxonomy, sim time"`

---

### Task 4: Compliance wall (strict TDD — this is the interview-defense core)

**Files:**
- Create: `src/encore/wall.py`, `tests/test_wall.py`

**Interfaces:**
- Consumes: everything from `domain.py`.
- Produces:
  - `WallConfig(max_retries_per_cycle: int = 3, cooldown_hours: int = 24, window_start_hour: int = 22, window_end_hour: int = 7, max_nudges_per_cycle: int = 2)` — defaults cite NPCI's Aug-2025 rule: 1 original execution + max 3 retries, executed in non-peak windows.
  - `SequenceState(original_decline: DeclineCode, retries_attempted: int, nudges_sent: int, last_attempt_hour: int | None, killed: bool)` frozen dataclass
  - `decide(action: ProposedAction, state: SequenceState, cfg: WallConfig) -> Decision` where `Decision(allowed: bool, reason: str)`; reason codes: `ok`, `hard_decline_terminal`, `sequence_killed`, `retry_cap_exceeded`, `cooldown_active`, `outside_execution_window`, `nudge_budget_exhausted`.
  - Rule precedence (documented, tested): killed > hard decline > cap > cooldown > window > budget.

- [ ] **Step 1: Write the adversarial test suite first — every test tries to break a rule**

```python
# tests/test_wall.py
import pytest

from encore.domain import ActionKind, DeclineCode, ProposedAction
from encore.wall import Decision, SequenceState, WallConfig, decide

CFG = WallConfig()


def retry(attempt_no: int, at_hour: int) -> ProposedAction:
    return ProposedAction(ActionKind.RETRY, "c1", "2026-09", 49900, at_hour, attempt_no)


def nudge(at_hour: int) -> ProposedAction:
    return ProposedAction(ActionKind.NUDGE, "c1", "2026-09", 49900, at_hour, 1)


def state(**kw) -> SequenceState:
    base = dict(original_decline=DeclineCode.INSUFFICIENT_FUNDS,
                retries_attempted=0, nudges_sent=0, last_attempt_hour=None, killed=False)
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
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_wall.py -q` → FAIL (module missing)

- [ ] **Step 3: Implement the wall**

```python
# src/encore/wall.py
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
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_wall.py -q` → PASS (11 tests)
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: compliance wall with adversarial test suite"`

---

### Task 5: Audit log and idempotent attempt ledger

**Files:**
- Create: `src/encore/audit.py`, `tests/test_audit.py`

**Interfaces:**
- Consumes: `attempt_id` from domain.
- Produces:
  - `AuditLog(path: Path)` with `append(record: dict) -> None` (adds nothing, writes one JSON line, flushes) and `read_all() -> list[dict]`.
  - `AttemptLedger(path: Path)` with `already_executed(aid: str) -> bool` and `record(aid: str) -> None`; persisted as one id per line so a crashed-and-restarted run cannot re-execute. This IS the idempotency mechanism (Razorpay's core Payments API has no idempotency-key header — application layer is the honest fix, and the README says so).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_audit.py
from pathlib import Path

from encore.audit import AttemptLedger, AuditLog


def test_audit_log_appends_and_reads_back(tmp_path: Path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append({"event": "decision", "reason": "ok"})
    log.append({"event": "execution", "outcome": "success"})
    assert [r["event"] for r in log.read_all()] == ["decision", "execution"]


def test_ledger_blocks_duplicate_execution(tmp_path: Path):
    led = AttemptLedger(tmp_path / "ledger.txt")
    assert not led.already_executed("c1:2026-09:retry:1")
    led.record("c1:2026-09:retry:1")
    assert led.already_executed("c1:2026-09:retry:1")


def test_ledger_survives_crash_restart(tmp_path: Path):
    p = tmp_path / "ledger.txt"
    AttemptLedger(p).record("c1:2026-09:retry:1")
    fresh = AttemptLedger(p)  # simulates process restart
    assert fresh.already_executed("c1:2026-09:retry:1")
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_audit.py -q` → FAIL

- [ ] **Step 3: Implement**

```python
# src/encore/audit.py
import json
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


class AttemptLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        if path.exists():
            self._seen = set(path.read_text(encoding="utf-8").split())

    def already_executed(self, aid: str) -> bool:
        return aid in self._seen

    def record(self, aid: str) -> None:
        self._seen.add(aid)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(aid + "\n")
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_audit.py -q` → PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: append-only audit log + crash-safe idempotency ledger"`

---

### Task 6: Portfolio simulator

The moat. Generative code — property-tested after writing rather than TDD, but the properties are strict.

**Files:**
- Create: `src/encore/simulator.py`, `tests/test_simulator.py`

**Interfaces:**
- Consumes: `DeclineCode`, `FailedDebit`, `HARD_DECLINES`, time helpers.
- Produces:
  - `RegimeConfig(salary_days: list[int], salary_day_weights: list[float], hard_decline_rate: float, issuer_down_daily_prob: float, uniform_credits: bool = False)` — the knobs the eval regimes turn.
  - `Customer(customer_id, amount_paise, salary_day, balance_paise, churn_intent: bool, revoked: bool)` (mutable dataclass; internal to simulation).
  - `Portfolio.generate(n_customers: int, regime: RegimeConfig, seed: int) -> Portfolio`
  - `Portfolio.run_cycle(days: int) -> list[FailedDebit]` — advances latent state hour by hour, attempts each customer's debit on their billing day, emits failures with decline codes.
  - `Portfolio.would_succeed(customer_id: str, at_hour: int) -> bool` — **the oracle**: resolves any hypothetical attempt from latent state (balance ≥ amount, issuer up, not revoked/churned). Both the simulated rail and the training-label generator call this.
  - `Portfolio.reply_events() -> list[ReplyEvent]` where `ReplyEvent(customer_id, at_hour, text)` — a seeded minority of customers send free-text replies after a nudge (Hinglish templates included).

- [ ] **Step 1: Implement the simulator**

```python
# src/encore/simulator.py
import random
from dataclasses import dataclass, field

from encore.domain import DAYS_PER_MONTH, HOURS_PER_DAY, DeclineCode, FailedDebit, day_of_month


@dataclass(frozen=True)
class RegimeConfig:
    salary_days: list[int]
    salary_day_weights: list[float]
    hard_decline_rate: float
    issuer_down_daily_prob: float
    uniform_credits: bool = False  # regime R2: destroys the salary-day signal


@dataclass(frozen=True)
class ReplyEvent:
    customer_id: str
    at_hour: int
    text: str


@dataclass
class Customer:
    customer_id: str
    amount_paise: int
    salary_day: int
    balance_paise: int
    daily_spend_paise: int
    billing_day: int
    churn_intent: bool
    revoked: bool = False


REPLY_TEMPLATES = [
    "salary {day} tarikh ko aayegi, tab try karna",
    "please retry after {day}th",
    "cancel karo yeh subscription",
    "band kar do isko",
    "will pay next week",
]


@dataclass
class Portfolio:
    customers: dict[str, Customer]
    regime: RegimeConfig
    rng: random.Random
    issuer_down_hours: set[int] = field(default_factory=set)
    _replies: list[ReplyEvent] = field(default_factory=list)

    @classmethod
    def generate(cls, n_customers: int, regime: RegimeConfig, seed: int) -> "Portfolio":
        rng = random.Random(seed)
        customers = {}
        for i in range(n_customers):
            cid = f"cust_{i:04d}"
            amount = rng.choice([19900, 29900, 49900, 99900])
            salary_day = rng.choices(regime.salary_days, regime.salary_day_weights)[0]
            customers[cid] = Customer(
                customer_id=cid,
                amount_paise=amount,
                salary_day=salary_day,
                balance_paise=rng.randint(0, 3 * amount),
                daily_spend_paise=rng.randint(1000, 15000),
                billing_day=rng.randint(1, DAYS_PER_MONTH),
                churn_intent=rng.random() < 0.05,
            )
        return cls(customers=customers, regime=regime, rng=rng)

    def _advance_hour(self, h: int) -> None:
        if h % HOURS_PER_DAY == 0:  # once per simulated day
            dom = day_of_month(h)
            if self.rng.random() < self.regime.issuer_down_daily_prob:
                start = h + self.rng.randint(0, 23)
                self.issuer_down_hours.update(range(start, start + self.rng.randint(2, 8)))
            for c in self.customers.values():
                credited = (
                    self.rng.random() < 1 / DAYS_PER_MONTH
                    if self.regime.uniform_credits
                    else dom == c.salary_day
                )
                if credited:
                    c.balance_paise += self.rng.randint(15_00000, 60_00000)  # salary credit
                c.balance_paise = max(0, c.balance_paise - c.daily_spend_paise)

    def would_succeed(self, customer_id: str, at_hour: int) -> bool:
        c = self.customers[customer_id]
        if c.revoked or c.churn_intent:
            return False
        if at_hour in self.issuer_down_hours:
            return False
        return c.balance_paise >= c.amount_paise

    def debit(self, customer_id: str, at_hour: int) -> DeclineCode | None:
        """Attempt a debit against latent state. None = success (balance deducted)."""
        c = self.customers[customer_id]
        if c.revoked:
            return DeclineCode.MANDATE_REVOKED
        if at_hour in self.issuer_down_hours:
            return DeclineCode.ISSUER_DOWN
        if c.balance_paise < c.amount_paise:
            return DeclineCode.INSUFFICIENT_FUNDS
        c.balance_paise -= c.amount_paise
        return None

    def run_cycle(self, days: int, cycle_id: str) -> list[FailedDebit]:
        failures: list[FailedDebit] = []
        for h in range(days * HOURS_PER_DAY):
            self._advance_hour(h)
            dom, hod = day_of_month(h), h % HOURS_PER_DAY
            for c in self.customers.values():
                if dom == c.billing_day and hod == 6:  # original execution, once
                    if self.rng.random() < self.regime.hard_decline_rate:
                        c.revoked = True
                    code = self.debit(c.customer_id, h)
                    if code is not None:
                        failures.append(FailedDebit(c.customer_id, cycle_id, c.amount_paise, code, h))
                        if self.rng.random() < 0.3:  # a minority reply to the eventual nudge
                            tmpl = self.rng.choice(REPLY_TEMPLATES)
                            self._replies.append(ReplyEvent(
                                c.customer_id, h + self.rng.randint(4, 48),
                                tmpl.format(day=c.salary_day),
                            ))
        return failures

    def reply_events(self) -> list[ReplyEvent]:
        return sorted(self._replies, key=lambda r: r.at_hour)
```

- [ ] **Step 2: Write property tests**

```python
# tests/test_simulator.py
from encore.domain import HARD_DECLINES
from encore.simulator import Portfolio, RegimeConfig

R0 = RegimeConfig(salary_days=[1, 7, 15], salary_day_weights=[0.6, 0.3, 0.1],
                  hard_decline_rate=0.08, issuer_down_daily_prob=0.05)


def test_same_seed_same_world():
    a = Portfolio.generate(200, R0, seed=42).run_cycle(60, "c1")
    b = Portfolio.generate(200, R0, seed=42).run_cycle(60, "c1")
    assert a == b


def test_different_seed_different_world():
    a = Portfolio.generate(200, R0, seed=42).run_cycle(60, "c1")
    b = Portfolio.generate(200, R0, seed=43).run_cycle(60, "c1")
    assert a != b


def test_failures_have_both_hard_and_soft_declines():
    fails = Portfolio.generate(500, R0, seed=7).run_cycle(60, "c1")
    codes = {f.decline for f in fails}
    assert codes & HARD_DECLINES
    assert codes - HARD_DECLINES
    assert len(fails) > 50  # enough events to measure anything


def test_oracle_agrees_with_debit_on_success():
    p = Portfolio.generate(100, R0, seed=9)
    p.run_cycle(30, "c1")
    for cid in list(p.customers)[:20]:
        if p.would_succeed(cid, 999_999):
            assert p.debit(cid, 999_999) is None
```

- [ ] **Step 3: Run** — `uv run pytest tests/test_simulator.py -q` → PASS
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat: latent-state portfolio simulator with oracle and regimes"`

---

### Task 7: Policies — interface, dumb baselines, and the scheduler that runs them

**Files:**
- Create: `src/encore/policies.py`, `src/encore/scheduler.py`, `tests/test_policies.py`, `tests/test_scheduler.py`

**Interfaces:**
- Consumes: domain, wall, audit, simulator.
- Produces:
  - `Policy` protocol: `propose(failed: FailedDebit, state: SequenceState, now_hour: int) -> ProposedAction | None` (None = park).
  - `ImmediateRetry3` — retries at now+1h, three times (deliberately dumb; the wall will deny out-of-window ones, which is itself reported).
  - `FixedSchedule` — retries at T+1, T+2, T+3 days at 23:00. This is Razorpay's own documented subscription auto-retry pattern — the baseline to beat.
  - `Scheduler.run(portfolio, failures, policy, wall_cfg, rail, audit_log, ledger) -> RunResult` where `RunResult(recovered_paise: int, attempts_executed: int, attempts_denied: int, nudges_sent: int, parked: int, denials_by_reason: dict[str, int])`. Every decision and execution is appended to the audit log. Sequence state updates: success ends the sequence; a reply of kind `cancel` kills it (wired fully in Task 9).
  - `SimulatedRail` implementing `execute(action) -> bool` via `portfolio.debit(...) is None`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scheduler.py
from pathlib import Path

from encore.audit import AttemptLedger, AuditLog
from encore.domain import DeclineCode, FailedDebit
from encore.policies import FixedSchedule, ImmediateRetry3
from encore.scheduler import Scheduler, SimulatedRail
from encore.simulator import Portfolio, RegimeConfig
from encore.wall import WallConfig

R0 = RegimeConfig(salary_days=[1, 7, 15], salary_day_weights=[0.6, 0.3, 0.1],
                  hard_decline_rate=0.08, issuer_down_daily_prob=0.05)


def build_world(seed=42):
    p = Portfolio.generate(300, R0, seed=seed)
    failures = p.run_cycle(60, "c1")
    return p, failures


def run(policy, tmp_path: Path, p, failures):
    sched = Scheduler(WallConfig())
    return sched.run(p, failures, policy,
                     SimulatedRail(p),
                     AuditLog(tmp_path / "audit.jsonl"),
                     AttemptLedger(tmp_path / "ledger.txt"))


def test_fixed_schedule_recovers_some_money(tmp_path):
    p, failures = build_world()
    result = run(FixedSchedule(), tmp_path, p, failures)
    assert result.recovered_paise > 0
    assert result.attempts_executed > 0


def test_no_hard_decline_is_ever_executed(tmp_path):
    p, failures = build_world()
    run(FixedSchedule(), tmp_path, p, failures)
    log = AuditLog(tmp_path / "audit.jsonl").read_all()
    hard_customers = {f.customer_id for f in failures
                     if f.decline in {DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED,
                                      DeclineCode.RISK_DECLINED}}
    executed = {r["customer_id"] for r in log if r["event"] == "execution"}
    assert not (hard_customers & executed)


def test_rerun_with_same_ledger_executes_nothing_new(tmp_path):
    p, failures = build_world()
    first = run(FixedSchedule(), tmp_path, p, failures)
    p2, failures2 = build_world()  # fresh world state, SAME ledger on disk
    second = run(FixedSchedule(), tmp_path, p2, failures2)
    assert first.attempts_executed > 0
    assert second.attempts_executed == 0  # idempotency held across "crash restart"


def test_immediate_retry_burns_attempts_on_window_denials(tmp_path):
    p, failures = build_world()
    result = run(ImmediateRetry3(), tmp_path, p, failures)
    assert result.denials_by_reason.get("outside_execution_window", 0) > 0
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_scheduler.py -q` → FAIL

- [ ] **Step 3: Implement policies**

```python
# src/encore/policies.py
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
```

- [ ] **Step 4: Implement the scheduler**

```python
# src/encore/scheduler.py
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
                              "amount_paise": action.amount_paise, "policy": policy.name})
                if success:
                    result.recovered_paise += action.amount_paise
                    break
                state = SequenceState(state.original_decline, state.retries_attempted + 1,
                                      state.nudges_sent, action.execute_at_hour, state.killed)
        return result
```

- [ ] **Step 5: Run all tests** — `uv run pytest -q` → PASS
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: policy interface, dumb baselines, idempotent scheduler"`

---

### Task 8: Learned timing policy — training data, model, policy wrapper

**Files:**
- Create: `src/encore/model.py`, `tests/test_model.py`

**Interfaces:**
- Consumes: simulator oracle, domain, policies protocol.
- Produces:
  - `featurize(decline: DeclineCode, candidate_hour: int, attempt_no: int, amount_paise: int) -> list[float]` — features: decline code one-hot (3 soft codes), day-of-month, hour-of-day, days-since-failure, attempt number, log-amount. No leakage: nothing from latent state.
  - `generate_training_data(regime, n_customers, seeds: list[int]) -> tuple[X, y]` — replays training-seed portfolios, samples candidate retry times uniformly inside wall-legal windows over the following 10 days, labels each with `portfolio.would_succeed(...)`.
  - `train(X, y) -> HistGradientBoostingClassifier`, `save/load` via pickle to `runs/model.pkl`.
  - `LearnedPolicy(model, cost_per_attempt_paise: int = 500)` implementing the `Policy` protocol: scores all wall-legal candidate hours in the next 10 days, picks argmax P(success); **parks when** `max_p * amount_paise < cost_per_attempt_paise` (the stopping rule — economics live in the policy, compliance lives in the wall).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_model.py
from encore.domain import DeclineCode
from encore.model import LearnedPolicy, featurize, generate_training_data, train
from encore.simulator import RegimeConfig

R0 = RegimeConfig(salary_days=[1, 7, 15], salary_day_weights=[0.6, 0.3, 0.1],
                  hard_decline_rate=0.08, issuer_down_daily_prob=0.05)


def test_featurize_is_fixed_width_and_numeric():
    v = featurize(DeclineCode.INSUFFICIENT_FUNDS, 100, 1, 49900)
    assert len(v) == 9
    assert all(isinstance(x, float) for x in v)


def test_training_data_has_both_labels():
    X, y = generate_training_data(R0, n_customers=200, seeds=[1, 2])
    assert len(X) == len(y) > 500
    assert 0.02 < sum(y) / len(y) < 0.98  # not degenerate


def test_model_beats_coin_flip_on_holdout_split():
    X, y = generate_training_data(R0, n_customers=300, seeds=[1, 2, 3])
    cut = int(len(X) * 0.8)
    clf = train(X[:cut], y[:cut])
    assert clf.score(X[cut:], y[cut:]) > 0.6


def test_learned_policy_parks_hopeless_low_amounts():
    X, y = generate_training_data(R0, n_customers=200, seeds=[1])
    clf = train(X, y)
    pol = LearnedPolicy(clf, cost_per_attempt_paise=10_000_000)  # absurd cost floor
    from encore.domain import FailedDebit
    from encore.wall import SequenceState
    failed = FailedDebit("cust_0001", "c1", 19900, DeclineCode.INSUFFICIENT_FUNDS, 100)
    state = SequenceState(DeclineCode.INSUFFICIENT_FUNDS, 0, 0, None, False)
    assert pol.propose(failed, state, 100) is None  # everything parks at that cost
```

- [ ] **Step 2: Run to verify failure** — FAIL (module missing)

- [ ] **Step 3: Implement**

```python
# src/encore/model.py
import math
import pickle
import random
from pathlib import Path

from sklearn.ensemble import HistGradientBoostingClassifier

from encore.domain import (HOURS_PER_DAY, ActionKind, DeclineCode, FailedDebit,
                           ProposedAction, day_of_month, hour_of_day)
from encore.simulator import Portfolio, RegimeConfig
from encore.wall import SequenceState, WallConfig, decide

SOFT_CODES = [DeclineCode.INSUFFICIENT_FUNDS, DeclineCode.ISSUER_DOWN,
              DeclineCode.GATEWAY_TIMEOUT]


def featurize(decline: DeclineCode, candidate_hour: int, attempt_no: int,
              amount_paise: int, failure_hour: int = 0) -> list[float]:
    onehot = [1.0 if decline == c else 0.0 for c in SOFT_CODES]
    return onehot + [
        float(day_of_month(candidate_hour)),
        float(hour_of_day(candidate_hour)),
        float((candidate_hour - failure_hour) / HOURS_PER_DAY),
        float(attempt_no),
        math.log(amount_paise),
        float(day_of_month(candidate_hour) in (1, 2, 7, 8)),  # near-payday flag
    ]


def _legal_candidates(failure_hour: int, cfg: WallConfig) -> list[int]:
    horizon = range(failure_hour + 1, failure_hour + 10 * HOURS_PER_DAY)
    return [h for h in horizon
            if cfg.window_start_hour <= hour_of_day(h) or hour_of_day(h) < cfg.window_end_hour]


def generate_training_data(regime: RegimeConfig, n_customers: int,
                           seeds: list[int]) -> tuple[list[list[float]], list[int]]:
    X: list[list[float]] = []
    y: list[int] = []
    cfg = WallConfig()
    for seed in seeds:
        p = Portfolio.generate(n_customers, regime, seed=seed)
        failures = p.run_cycle(60, f"train_{seed}")
        rng = random.Random(seed * 7919)
        for f in failures:
            if f.decline not in SOFT_CODES:
                continue
            for h in rng.sample(_legal_candidates(f.at_hour, cfg), 12):
                X.append(featurize(f.decline, h, 1, f.amount_paise, f.at_hour))
                y.append(int(p.would_succeed(f.customer_id, h)))
    return X, y


def train(X, y) -> HistGradientBoostingClassifier:
    clf = HistGradientBoostingClassifier(random_state=0)
    clf.fit(X, y)
    return clf


def save(clf, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(clf))


def load(path: Path) -> HistGradientBoostingClassifier:
    return pickle.loads(path.read_bytes())


class LearnedPolicy:
    """Chooses WHEN inside the wall; never WHETHER something is allowed."""
    name = "encore_learned"

    def __init__(self, clf, cost_per_attempt_paise: int = 500) -> None:
        self.clf = clf
        self.cost = cost_per_attempt_paise
        self._cfg = WallConfig()

    def propose(self, failed: FailedDebit, state: SequenceState,
                now_hour: int) -> ProposedAction | None:
        if state.retries_attempted >= self._cfg.max_retries_per_cycle:
            return None
        candidates = [h for h in _legal_candidates(now_hour, self._cfg)]
        feats = [featurize(failed.decline, h, state.retries_attempted + 1,
                           failed.amount_paise, failed.at_hour) for h in candidates]
        if not feats:
            return None
        probs = self.clf.predict_proba(feats)[:, 1]
        best = max(range(len(candidates)), key=lambda i: probs[i])
        if probs[best] * failed.amount_paise < self.cost:
            return None  # stopping rule: expected recovery below action cost
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, candidates[best],
                              state.retries_attempted + 1)
```

- [ ] **Step 4: Run** — `uv run pytest tests/test_model.py -q` → PASS (the training test takes ~30s; that's acceptable)
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: oracle-labeled training data, HGB timing model, learned policy with stopping rule"`

---

### Task 9: Reply parser (keyword fallback + Claude) and the kill switch

**Files:**
- Create: `src/encore/parser.py`, `tests/test_parser.py`, `data/reply_eval.jsonl` (40 labeled replies)

**Interfaces:**
- Consumes: `ReplyEvent` from simulator.
- Produces:
  - `ReplyIntent(BaseModel)`: `kind: Literal["promise_to_pay","cancel","dispute","other"]`, `promise_day: int | None` (day of month 1–30).
  - `parse_keyword(text: str) -> ReplyIntent` — deterministic regex fallback, no network.
  - `parse_llm(text: str, model: str = "claude-sonnet-5") -> ReplyIntent` — Anthropic call, JSON-schema-constrained, validated by pydantic; any validation failure falls back to `parse_keyword`.
  - `evaluate(parser_fn, eval_path) -> dict` — accuracy on the labeled set; the CLI prints keyword vs Haiku vs Sonnet as a table (the evidence behind the model choice).
  - Kill wiring: `Scheduler.run` already accepts `killed_customers: set[str]`; the eval runner builds that set from replies parsed as `cancel` **before** scheduling — a cancel always wins over any retry.

- [ ] **Step 1: Write failing tests (fallback only — LLM tests are the eval script, not unit tests)**

```python
# tests/test_parser.py
from encore.parser import ReplyIntent, parse_keyword


def test_cancel_hinglish():
    assert parse_keyword("band kar do isko").kind == "cancel"
    assert parse_keyword("cancel karo yeh subscription").kind == "cancel"


def test_promise_with_tarikh_date():
    intent = parse_keyword("salary 5 tarikh ko aayegi, tab try karna")
    assert intent.kind == "promise_to_pay"
    assert intent.promise_day == 5


def test_unknown_text_is_other_never_a_guess():
    assert parse_keyword("kya haal hai bhai").kind == "other"


def test_intent_schema_rejects_out_of_range_day():
    import pytest
    with pytest.raises(ValueError):
        ReplyIntent(kind="promise_to_pay", promise_day=42)
```

- [ ] **Step 2: Run to verify failure** — FAIL

- [ ] **Step 3: Implement**

```python
# src/encore/parser.py
import json
import os
import re
from typing import Literal

from pydantic import BaseModel, Field

CANCEL_WORDS = re.compile(r"\b(cancel|band|stop|unsubscribe|nahi chahiye)\b", re.I)
PROMISE_DAY = re.compile(r"\b(\d{1,2})\s*(tarikh|th|st|nd|rd)\b", re.I)
PROMISE_WORDS = re.compile(r"\b(salary|pay|paisa|baad|after|next week|retry)\b", re.I)


class ReplyIntent(BaseModel):
    kind: Literal["promise_to_pay", "cancel", "dispute", "other"]
    promise_day: int | None = Field(default=None, ge=1, le=30)


def parse_keyword(text: str) -> ReplyIntent:
    if CANCEL_WORDS.search(text):
        return ReplyIntent(kind="cancel")
    day_match = PROMISE_DAY.search(text)
    if day_match and 1 <= int(day_match.group(1)) <= 30:
        return ReplyIntent(kind="promise_to_pay", promise_day=int(day_match.group(1)))
    if PROMISE_WORDS.search(text):
        return ReplyIntent(kind="promise_to_pay")
    return ReplyIntent(kind="other")


SYSTEM = """You classify a subscription customer's reply about a failed payment.
Return ONLY JSON: {"kind": "promise_to_pay"|"cancel"|"dispute"|"other",
"promise_day": <int 1-30 or null>}. promise_day is the day of month they say
money arrives. Replies may be Hindi/Hinglish. Do not invent a day."""


def parse_llm(text: str, model: str = "claude-sonnet-5") -> ReplyIntent:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=model, max_tokens=100, system=SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    try:
        return ReplyIntent(**json.loads(msg.content[0].text))
    except Exception:
        return parse_keyword(text)  # the model never gets to break the pipeline
```

- [ ] **Step 4: Build the labeled eval set** — `data/reply_eval.jsonl`, 40 lines, mix of Hinglish/English/edge cases, hand-labeled. Ten examples to seed (write the remaining 30 in the same shape — vary spellings, add dispute cases like "maine to pay kar diya tha", ambiguous dates, pure noise):

```json
{"text": "salary 5 tarikh ko aayegi, tab try karna", "kind": "promise_to_pay", "promise_day": 5}
{"text": "band kar do isko", "kind": "cancel", "promise_day": null}
{"text": "cancel karo please", "kind": "cancel", "promise_day": null}
{"text": "will pay after 7th", "kind": "promise_to_pay", "promise_day": 7}
{"text": "maine already pay kar diya, phir se kyu kata?", "kind": "dispute", "promise_day": null}
{"text": "next month se mat kaatna paise", "kind": "cancel", "promise_day": null}
{"text": "1 tarikh ko salary credit hoti hai", "kind": "promise_to_pay", "promise_day": 1}
{"text": "ok", "kind": "other", "promise_day": null}
{"text": "kaun ho aap log", "kind": "other", "promise_day": null}
{"text": "retry on 15th please", "kind": "promise_to_pay", "promise_day": 15}
```

- [ ] **Step 5: Run tests** — `uv run pytest tests/test_parser.py -q` → PASS
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: reply parser — keyword fallback, Claude backend, labeled eval set"`

---

### Task 10: Eval harness — three regimes × three policies, violations must be zero

**Files:**
- Create: `src/encore/evaluate.py`, `tests/test_evaluate.py`

**Interfaces:**
- Consumes: everything so far.
- Produces:
  - `REGIMES: dict[str, RegimeConfig]` — `"r0_base"` (train), `"r1_shifted"` (held-out: salary days `[3, 10, 25]` with weights `[0.2, 0.3, 0.5]`, `hard_decline_rate=0.15`, `issuer_down_daily_prob=0.12`), `"r2_no_signal"` (`uniform_credits=True`).
  - `run_matrix(seeds: list[int], out_dir: Path) -> dict` — for each regime × policy (immediate_x3, fixed_t123, encore_learned): fresh portfolio on **held-out seeds (100+)**, replies parsed → kill set, scheduler run, metrics per cell: `recovered_per_1000_failures_paise`, `recovery_per_attempt_paise`, `max_contacts_per_customer`, `parked_paise`, `denials_by_reason`, `compliance_violations` (count of executions the wall would have denied — recomputed post-hoc from the audit log, must be 0). Writes `runs/eval.json`.
  - Training always and only on seeds 1–5, regime r0. Eval seeds start at 100. This split is stated in the README.

- [ ] **Step 1: Write the post-hoc violation checker test first**

```python
# tests/test_evaluate.py
from pathlib import Path

from encore.evaluate import REGIMES, count_violations, run_matrix


def test_regimes_are_distinct():
    assert REGIMES["r1_shifted"].salary_days != REGIMES["r0_base"].salary_days
    assert REGIMES["r2_no_signal"].uniform_credits


def test_matrix_runs_and_no_policy_violates_the_wall(tmp_path: Path):
    results = run_matrix(seeds=[100], out_dir=tmp_path, n_customers=150)
    for cell, metrics in results.items():
        assert metrics["compliance_violations"] == 0, f"{cell} violated the wall"
    assert results["r1_shifted/encore_learned"]["recovered_per_1000_failures_paise"] >= 0


def test_violation_checker_actually_catches_violations(tmp_path: Path):
    # A forged audit log with an execution on a hard-declined, revoked customer
    from encore.audit import AuditLog
    log = AuditLog(tmp_path / "forged.jsonl")
    log.append({"event": "execution", "customer_id": "c1", "attempt_id": "c1:x:retry:5",
                "at_hour": 12, "outcome": "failure", "amount_paise": 100,
                "original_decline": "mandate_revoked", "attempt_no": 5})
    assert count_violations(log.read_all()) > 0
```

- [ ] **Step 2: Run to verify failure** — FAIL

- [ ] **Step 3: Implement** `evaluate.py`: build the regime dict exactly as specified in Interfaces; `run_matrix` loops regimes × policies, generates portfolio per (regime, seed), collects failures + replies, builds the kill set from `parse_keyword` (LLM parsing is a CLI flag, not a hard dependency), runs the scheduler, computes the metrics dict per cell, recomputes violations from the audit log with `count_violations` (replays each execution record against a reconstructed `SequenceState` and the wall — an execution whose reconstruction the wall denies counts as a violation; records must therefore carry `original_decline` and `attempt_no`, so extend the scheduler's execution record with those two fields in this task), writes `runs/eval.json`. The scheduler change is two added keys in one `audit.append` call.

- [ ] **Step 4: Run** — `uv run pytest tests/test_evaluate.py -q` → PASS, then full suite `uv run pytest -q` → PASS
- [ ] **Step 5: Run the real matrix** — `uv run python -m encore.evaluate` (add `if __name__ == "__main__": run_matrix(seeds=[100,101,102], out_dir=Path("runs"), n_customers=500)`) and eyeball `runs/eval.json`: the learned policy should beat both baselines on r1 and collapse toward them on r2. **Whatever the numbers actually are is what gets reported.** If the learned policy loses on r1, that goes in BROKELOG and gets diagnosed — do not tune the simulator until it wins.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: regime-matrix eval harness with post-hoc wall-violation checker"`

---

### Task 11: Razorpay demo slice — real Payment Links driven by the sequencer

**Files:**
- Create: `src/encore/demo.py`
- Modify: `src/encore/razorpay_client.py` (add polling helper)

**Interfaces:**
- Consumes: `RazorpayClient`, scheduler, learned policy.
- Produces:
  - `poll_until_terminal(client, link_id, timeout_s: int = 300, interval_s: int = 5) -> str` — polls `fetch_payment_link` until status in `{"paid", "cancelled", "expired"}` or timeout; returns final status.
  - `run_demo_slice(n: int = 3)` — takes the first `n` soft-decline failures from a seeded portfolio, and for each: creates a real test-mode Payment Link (reference_id = the attempt_id, so idempotency extends to the real rail), prints the short URL for on-camera payment with `success@razorpay` / `failure@razorpay`, polls, writes real outcomes into the same audit log format. README states plainly: bulk metrics come from the simulator; the demo slice proves the rail integration is real.

- [ ] **Step 1: Implement** both functions (polling is a `while` loop with `time.sleep`; demo prints a numbered list of URLs and waits). No unit tests for network code — the spike + on-camera run is the verification; a `--dry-run` flag exercises the code path against `SimulatedRail`.
- [ ] **Step 2: Verify manually** — `uv run python -m encore.demo --n 2`, pay one link with `success@razorpay`, fail one with `failure@razorpay`, confirm both outcomes land in `runs/demo_audit.jsonl`. Paste the terminal output into `docs/spike-notes.md`.
- [ ] **Step 3: Commit** — `git add -A && git commit -m "feat: real test-mode demo slice — payment links + polling through the same audit path"`

---

### Task 12: CLI and HTML scoreboard

**Files:**
- Create: `src/encore/cli.py`, `src/encore/report.py`, `tests/test_report.py`

**Interfaces:**
- Produces:
  - `encore eval --seeds 100,101,102 --customers 500` → runs the matrix, writes `runs/eval.json`.
  - `encore report` → reads `runs/eval.json`, writes `runs/scoreboard.html` — a single static page: policy × regime table (rupees formatted from paise), denial-reason breakdown, parked-revenue line, violations row (must display 0), and a per-customer audit-trail section for one sample customer.
  - `encore parse-eval` → prints keyword vs `claude-haiku-4-5` vs `claude-sonnet-5` accuracy on `data/reply_eval.jsonl` (needs API key; prints keyword-only without one).
  - `encore demo --n 3` → Task 11's slice.
  - `report.py` builds HTML with f-strings only (no template dependency); `test_report.py` asserts the generated HTML contains the violations row and one formatted rupee figure from a fixture eval.json.
- [ ] **Steps:** failing test for `report.render(eval_dict) -> str` → implement → `argparse` CLI wiring all four commands → run `uv run encore report` on real `runs/eval.json` and open the HTML → commit `"feat: cli + static scoreboard"`.

---

### Task 13: README, AGENTS.md, repo polish for the AI screener

**Files:**
- Create: `AGENTS.md`; Modify: `README.md`

README structure, in this order (the first screening reader is likely an AI agent — front-load the measurable):
1. One-paragraph problem with the NPCI numbers (20M+ mandates revoked/month; 55–90% AutoPay execution failures, Aug 2025; steady-state 8–15% vs 2–3% cards) with source links.
2. **The metrics table** — pasted from the real `runs/eval.json`, whatever it says.
3. Architecture diagram (mermaid): simulator → policy → wall → rail → audit → report; LLM box hanging off "replies" only.
4. Quickstart: `uv sync && uv run pytest && uv run encore eval && uv run encore report`.
5. "Where we chose not to use AI" — the wall, the stopping rule, money math; the parser eval table justifying the model choice.
6. Prior art: Stripe Smart Retries, Chargebee Revive, GoCardless Success+, Razorpay's fixed T+1/T+2/T+3 (our baseline) and Razorpay Intelligent Payment Retry (checkout-time, out of scope). One line of delta.
7. Honest limitations: 30-day months, simulator-relative rupees (policy comparison, not real-world lift), what test mode cannot prove, NPCI semantics "modeled on, with citations" — never "compliant".
`AGENTS.md`: repo map, how to run each command, where the seeds/regimes are defined, the wall-purity and paise rules restated.
- [ ] Commit: `"docs: README with measured results, AGENTS.md for agent readers"`.

---

### Task 14: Submission assets (not code — do last)

- **Demo script** (`docs/demo-script.md`): the six beats from the dossier with exact commands; rehearse on one fixed disclosed seed; metrics quoted only from held-out seeds.
- **Video:** OBS screen recording; under 5:00; terminal time under 90 seconds; show the Razorpay test dashboard when the demo-slice link is paid.
- **"What broke" essay:** assembled ONLY from `BROKELOG.md` entries with their commit hashes. Pick the 2–3 deepest entries, write root cause → evidence → fix → what's still open.
- **Form:** track = AI Revenue Recovery; repo URL; video link (unlisted); your in-person and 6/12-month answers.

---

## Self-Review (done at plan-writing time)

- **Coverage:** every dossier commitment maps to a task — compliance wall + adversarial tests (T4), idempotency/crash-restart (T5, T7), three regimes incl. signal-free (T10), Razorpay baseline (T7), stopping rule (T8), Hinglish parser with fallback + model-choice evidence (T9, T12), real test-mode slice (T2, T11), audit trail (T5 onward), violations-zero enforcement (T10), broke-log system (T1), AI-screener repo shape (T13).
- **Type consistency check:** `SequenceState` fields consistent across T4/T7/T8; `attempt_id` used by ledger and demo slice reference_id; `RegimeConfig.uniform_credits` consumed in T6 and T10; execution audit records gain `original_decline`/`attempt_no` in T10 and the violation checker consumes exactly those.
- **Known simplifications stated for the panel:** 30-day months; sequences processed per-failure rather than a global interleaved event queue (documented; a global queue is a stretch refactor, not a correctness issue for policy comparison); nudges in the simulator raise reply events but do not themselves change balances.
