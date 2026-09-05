# Recovery Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Encore from a policy-comparison harness into a recovery agent that detects real failed test-mode payments, decides inside the compliance wall, nudges, reads the (simulated) customer reply, collects through a real Razorpay Payment Link, and shows rupees recovered on a live board over a batch of 50+; plus one new measured experiment, a promise-aware policy that makes the reply parser the recovery mechanism.

**Architecture:** New modules sit beside the existing ones and reuse them: `sources.py` (failure sources → `FailedDebit`), `policies.PromiseAwarePolicy` (reply-driven timing inside the wall), `clock.py`, `rails.py` (sync simulated rail and pending-capable Razorpay link rail), `agent.py` (event loop over sim hours: replies, wall decisions, executions, polling), `board.py` (pure transform + f-string HTML). `wall.py` and `scheduler.py` are not modified. The eval matrix grows from 18 to 28 cells (4 regimes × 7 policies) and the 18 existing cells must stay byte-identical.

**Tech Stack:** Python 3.13, uv, pytest, ruff, httpx (Razorpay REST), pydantic (parser output). No new dependencies.

## Global Constraints

- Money is integer paise everywhere. Floats only in derived display.
- `wall.py` stays pure: no I/O, no clock, no randomness. The clock is injected into the agent, never into the wall.
- No LLM call on the money path. Parser output goes through pydantic `ReplyIntent`, then the wall.
- All randomness from seeded `random.Random` instances passed explicitly.
- Run `uv run pytest -q` and `uv run ruff check .` before every commit (line-length 100, py313).
- BROKELOG entry BEFORE fixing anything that fails unexpectedly, reverses a decision, or contradicts docs.
- Existing 18 eval cells must not change to the paise (pinned by a snapshot test in Task 3).
- Commit messages are written for a reader who was not there.
- Working directory: `C:\dev\encore\.claude\worktrees\buildathon-project-strategy-71f7cb`, branch `claude/buildathon-project-strategy-71f7cb` (web-build branch already merged; 116 tests green).

---

### Task 0: Finish the A0 spike and record it

**Files:**
- Already created: `scripts/spike_failed_payments.py` (create / list)
- Modify: `docs/spike-notes.md` (append a section)
- Modify: `BROKELOG.md` only if the docs are contradicted

**Interfaces:**
- Produces: the exact `error_reason` string for the insufficient-funds test card, whether `notes.customer_id` propagates from link to payment, and whether failed payments appear in `GET /v1/payments`. Task 2's mapping table and correlation rule depend on this.

- [ ] **Step 1: Operator fails the spike link** — open `https://rzp.io/rzp/WGtqU1p` (link `plink_TX8I88IJxQ3hq5`, notes `{"customer_id": "cust_spike"}`), enter contact `9123456789`, choose Cards, card `4100 2800 0008 0001`, any CVV, any future expiry. Expect "Payment failed".

- [ ] **Step 2: List failed payments**

Run: `uv run python scripts/spike_failed_payments.py list`
Expected: one JSON line with `"status": "failed"`, an `error_reason` (record the exact string), and either `"notes": {"customer_id": "cust_spike", ...}` or `"notes": {}`.

- [ ] **Step 3: Append to `docs/spike-notes.md`** a section `## A0 spike — failed-payment detection (2026-09-02)` containing the verbatim create and list output, and three one-line findings: (a) failed attempts do / do not appear in `GET /v1/payments`; (b) notes do / do not propagate; (c) the exact `error_reason` value. If (a) or (b) contradicts the docs cited in the design plan, write the BROKELOG entry first.

- [ ] **Step 4: Commit**

```bash
git add scripts/spike_failed_payments.py docs/spike-notes.md BROKELOG.md
git commit -m "spike: failed-payment detection through the Payments API, with notes propagation checked"
```

---

### Task 1: RazorpayClient gains `notes` and `list_payments`

**Files:**
- Modify: `src/encore/razorpay_client.py`
- Create: `tests/test_razorpay_client.py`

**Interfaces:**
- Produces: `RazorpayClient(transport: httpx.BaseTransport | None = None)`; `create_payment_link(amount_paise: int, description: str, reference_id: str, notes: dict[str, str] | None = None) -> dict`; `list_payments(from_ts: int, to_ts: int, count: int = 100, skip: int = 0) -> list[dict]` (unwraps `items`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_razorpay_client.py
import json

import httpx
import pytest

from encore.razorpay_client import RazorpayClient


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")


def test_list_payments_sends_the_window_and_unwraps_items(keys):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"entity": "collection", "count": 1,
                                         "items": [{"id": "pay_1", "status": "failed"}]})

    client = RazorpayClient(transport=httpx.MockTransport(handler))
    assert client.list_payments(100, 200) == [{"id": "pay_1", "status": "failed"}]
    assert "from=100" in seen["url"] and "to=200" in seen["url"] and "count=100" in seen["url"]


def test_create_payment_link_sends_notes_only_when_given(keys):
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "plink_1", "status": "created", "short_url": "u"})

    client = RazorpayClient(transport=httpx.MockTransport(handler))
    client.create_payment_link(19900, "d", "ref-1")
    client.create_payment_link(19900, "d", "ref-2", notes={"customer_id": "cust_0001"})
    assert "notes" not in bodies[0]
    assert bodies[1]["notes"] == {"customer_id": "cust_0001"}
    assert bodies[1]["amount"] == 19900 and isinstance(bodies[1]["amount"], int)
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_razorpay_client.py -q` → fails: unexpected keyword `transport` / no attribute `list_payments`.

- [ ] **Step 3: Implement**

```python
# src/encore/razorpay_client.py — replace __init__ and create_payment_link, add list_payments
class RazorpayClient:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        auth = (os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"])
        # transport is injected only by tests (httpx.MockTransport); production uses httpx's default
        self._http = httpx.Client(base_url=BASE, auth=auth, timeout=20.0, transport=transport)

    def create_payment_link(self, amount_paise: int, description: str, reference_id: str,
                            notes: dict[str, str] | None = None) -> dict:
        body: dict = {"amount": amount_paise, "currency": "INR",
                      "description": description, "reference_id": reference_id}
        if notes:
            body["notes"] = notes
        resp = self._http.post("/payment_links", json=body)
        resp.raise_for_status()
        return resp.json()

    def list_payments(self, from_ts: int, to_ts: int, count: int = 100, skip: int = 0) -> list[dict]:
        """GET /v1/payments in a Unix-time window. Failed attempts DO appear here
        with status="failed" and error_reason -- unlike a Payment Link's own
        payments[] array, which only ever lists captured payments (docs/spike-notes.md, A0)."""
        resp = self._http.get("/payments", params={"from": from_ts, "to": to_ts,
                                                   "count": count, "skip": skip})
        resp.raise_for_status()
        return resp.json().get("items", [])
```

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_razorpay_client.py -q` → 2 passed. Then full suite + ruff.

- [ ] **Step 5: Commit** — `git commit -am "feat: Payments API listing and link notes on the Razorpay client"`

---

### Task 2: Failure sources

**Files:**
- Create: `src/encore/sources.py`
- Create: `tests/test_sources.py`

**Interfaces:**
- Consumes: `FailedDebit`, `DeclineCode`, `HOURS_PER_DAY` from `encore.domain`; `Portfolio` from `encore.simulator`; `RazorpayClient.list_payments`.
- Produces: `FailureSource` Protocol with `failures() -> list[FailedDebit]`; `SimulatedFailureSource(portfolio, cycle_id, days=30)`; `RazorpayFailureSource(client, from_ts, to_ts, cycle_id, anchor_ts)` with attribute `unmapped: list[dict]` after `failures()`; `ERROR_REASON_TO_DECLINE`; `map_error_reason(reason) -> DeclineCode | None`; `sim_hour(created_at, anchor_ts) -> int`; `IST_OFFSET_S`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sources.py
from encore.domain import DeclineCode
from encore.simulator import Portfolio, RegimeConfig
from encore.sources import (IST_OFFSET_S, RazorpayFailureSource, SimulatedFailureSource,
                            map_error_reason, sim_hour)

R0 = RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05)
ANCHOR = 1788287400  # 2026-09-01 00:00 IST as a Unix timestamp (18:30 UTC the day before)


class FakeClient:
    def __init__(self, items):
        self.items = items

    def list_payments(self, from_ts, to_ts, count=100, skip=0):
        return self.items


def _payment(**over):
    base = {"id": "pay_1", "status": "failed", "amount": 19900, "created_at": ANCHOR + 14 * 3600,
            "error_reason": "insufficient_funds", "notes": {"customer_id": "cust_0042"}}
    base.update(over)
    return base


def test_mapping_is_explicit_and_unknown_is_none():
    assert map_error_reason("insufficient_funds") is DeclineCode.INSUFFICIENT_FUNDS
    assert map_error_reason("gateway_technical_error") is DeclineCode.GATEWAY_TIMEOUT
    assert map_error_reason("card_declined") is None
    assert map_error_reason(None) is None


def test_sim_hour_keeps_ist_hour_of_day_and_counts_days_from_anchor():
    assert sim_hour(ANCHOR, ANCHOR) == 0
    assert sim_hour(ANCHOR + 14 * 3600, ANCHOR) == 14
    assert sim_hour(ANCHOR + 2 * 86400 + 23 * 3600, ANCHOR) == 2 * 24 + 23
    assert IST_OFFSET_S == 19800


def test_razorpay_source_yields_failed_debits_with_customer_from_notes():
    src = RazorpayFailureSource(FakeClient([_payment()]), ANCHOR, ANCHOR + 86400, "live", ANCHOR)
    [f] = src.failures()
    assert f.customer_id == "cust_0042" and f.amount_paise == 19900
    assert f.decline is DeclineCode.INSUFFICIENT_FUNDS and f.at_hour == 14 and f.cycle_id == "live"
    assert src.unmapped == []


def test_razorpay_source_skips_non_failed_and_parks_unmapped():
    items = [_payment(status="captured"), _payment(id="pay_2", error_reason="card_declined"),
             _payment(id="pay_3", notes={})]
    src = RazorpayFailureSource(FakeClient(items), ANCHOR, ANCHOR + 86400, "live", ANCHOR)
    fails = src.failures()
    assert [f.customer_id for f in fails] == ["rzp:pay_3"]
    assert src.unmapped == [{"payment_id": "pay_2", "customer_id": "cust_0042",
                             "error_reason": "card_declined", "amount_paise": 19900}]


def test_simulated_source_equals_run_cycle():
    a = Portfolio.generate(100, R0, seed=7)
    b = Portfolio.generate(100, R0, seed=7)
    assert SimulatedFailureSource(a, "c1").failures() == b.run_cycle(30, "c1")
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_sources.py -q` → ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# src/encore/sources.py
"""Where failed debits come from. Two sources, one shape (FailedDebit), so the
agent and the eval harness never care which rail produced a failure."""
from typing import Protocol

from encore.domain import HOURS_PER_DAY, DeclineCode, FailedDebit
from encore.simulator import Portfolio

IST_OFFSET_S = 5 * 3600 + 30 * 60

# Razorpay `error_reason` -> our decline taxonomy. Explicit and short on
# purpose: a reason not in this table is an EXCEPTION the agent reports (parked,
# reason "unmapped_error_reason"), never a guess about whether a retry is legal.
# Strings verified in docs/spike-notes.md (A0) and razorpay.com/docs/errors/error-reasons.
ERROR_REASON_TO_DECLINE: dict[str, DeclineCode] = {
    "insufficient_funds": DeclineCode.INSUFFICIENT_FUNDS,
    "gateway_technical_error": DeclineCode.GATEWAY_TIMEOUT,
}


def map_error_reason(reason: str | None) -> DeclineCode | None:
    return ERROR_REASON_TO_DECLINE.get(reason or "")


def sim_hour(created_at: int, anchor_ts: int) -> int:
    """Unix timestamp -> simulated hour: whole IST days since the anchor x 24,
    plus the IST hour of day. Hour-of-day is preserved so the wall's 22:00-07:00
    execution window means the same thing on real timestamps."""
    local, anchor_local = created_at + IST_OFFSET_S, anchor_ts + IST_OFFSET_S
    days = local // 86400 - anchor_local // 86400
    return days * HOURS_PER_DAY + (local % 86400) // 3600


class FailureSource(Protocol):
    def failures(self) -> list[FailedDebit]: ...


class SimulatedFailureSource:
    def __init__(self, portfolio: Portfolio, cycle_id: str, days: int = 30) -> None:
        self._p, self._cycle_id, self._days = portfolio, cycle_id, days

    def failures(self) -> list[FailedDebit]:
        return self._p.run_cycle(self._days, self._cycle_id)


class RazorpayFailureSource:
    """Failed payments from GET /v1/payments in [from_ts, to_ts]. customer_id comes
    from the payment's notes (set on the originating Payment Link), else
    "rzp:<payment_id>" so nothing is silently dropped."""

    def __init__(self, client, from_ts: int, to_ts: int, cycle_id: str, anchor_ts: int) -> None:
        self._client, self._from, self._to = client, from_ts, to_ts
        self._cycle_id, self._anchor = cycle_id, anchor_ts
        self.unmapped: list[dict] = []

    def failures(self) -> list[FailedDebit]:
        out: list[FailedDebit] = []
        self.unmapped = []
        for p in self._client.list_payments(self._from, self._to):
            if p.get("status") != "failed":
                continue
            cid = (p.get("notes") or {}).get("customer_id") or f"rzp:{p['id']}"
            code = map_error_reason(p.get("error_reason"))
            if code is None:
                self.unmapped.append({"payment_id": p["id"], "customer_id": cid,
                                      "error_reason": p.get("error_reason"),
                                      "amount_paise": int(p["amount"])})
                continue
            out.append(FailedDebit(cid, self._cycle_id, int(p["amount"]), code,
                                   sim_hour(int(p["created_at"]), self._anchor)))
        return out
```

If Task 0 showed notes do NOT propagate: keep the code, and have `encore seed-live` (Task 9) write `runs/live_originals.json` mapping `order_id` → `customer_id`; add an optional `order_map: dict[str, str]` constructor argument consulted before the `rzp:` fallback, with a test.

- [ ] **Step 4: Run tests, full suite, ruff.** Expected: 5 passed in the new file.

- [ ] **Step 5: Commit** — `git add src/encore/sources.py tests/test_sources.py && git commit -m "feat: failure sources -- simulated cycle and real Payments-API failures share one shape"`

---

### Task 3: Simulator promise noise, byte-identity pinned first

**Files:**
- Modify: `src/encore/simulator.py` (`RegimeConfig`, `run_cycle` reply block)
- Modify: `tests/test_simulator.py` (append)

**Interfaces:**
- Produces: `RegimeConfig(..., promise_error_days: int = 0, false_promise_rate: float = 0.0)`. When both are zero no RNG is drawn, so every existing regime is unchanged.

- [ ] **Step 1: Pin the pre-change digest.** Run BEFORE editing the simulator:

```bash
uv run python -c "import hashlib; from encore.simulator import Portfolio, RegimeConfig; R0=RegimeConfig([1,7,15],[0.6,0.3,0.1],0.08,0.05); p=Portfolio.generate(200,R0,seed=100); f=p.run_cycle(30,'snap'); payload=[(x.customer_id,str(x.decline),x.at_hour) for x in f]+[(r.customer_id,r.at_hour,r.text) for r in p.reply_events()]; print(hashlib.sha256(repr(payload).encode()).hexdigest())"
```

Paste the printed hex into `PINNED` below.

- [ ] **Step 2: Write the tests**

```python
# tests/test_simulator.py — append
import hashlib

PINNED = "<hex from Step 1>"


def _digest(regime, seed=100, n=200):
    p = Portfolio.generate(n, regime, seed=seed)
    f = p.run_cycle(30, "snap")
    payload = [(x.customer_id, str(x.decline), x.at_hour) for x in f] + \
              [(r.customer_id, r.at_hour, r.text) for r in p.reply_events()]
    return hashlib.sha256(repr(payload).encode()).hexdigest()


def test_regimes_without_noise_fields_are_byte_identical_to_the_pre_noise_simulator():
    assert _digest(RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05)) == PINNED


def test_noise_fields_change_promised_days_but_nothing_else():
    clean = RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05)
    noisy = RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05,
                         promise_error_days=2, false_promise_rate=0.3)
    a, b = Portfolio.generate(200, clean, seed=100), Portfolio.generate(200, noisy, seed=100)
    fa, fb = a.run_cycle(30, "c"), b.run_cycle(30, "c")
    assert [(x.customer_id, x.at_hour) for x in fa] == [(x.customer_id, x.at_hour) for x in fb]
    ra, rb = a.reply_events(), b.reply_events()
    assert [(r.customer_id, r.at_hour) for r in ra] == [(r.customer_id, r.at_hour) for r in rb]
    assert any(x.text != y.text for x, y in zip(ra, rb, strict=True))
```

The second test needs the noise draws to come from a SEPARATE rng stream so failures and reply hours stay identical; see Step 4.

- [ ] **Step 3: Run** — first test passes already (digest pinned on current code), second fails on the unexpected keyword.

- [ ] **Step 4: Implement**

```python
# simulator.py — RegimeConfig
@dataclass(frozen=True)
class RegimeConfig:
    salary_days: list[int]
    salary_day_weights: list[float]
    hard_decline_rate: float
    issuer_down_daily_prob: float
    uniform_credits: bool = False  # regime R2: destroys the salary-day signal
    # Promise noise (regime R3). Both zero => no RNG drawn, older regimes byte-identical.
    promise_error_days: int = 0     # promised day is off by up to +/- this many days
    false_promise_rate: float = 0.0  # share of promises naming a random day

# simulator.py — Portfolio: add a field
    _noise_rng: random.Random | None = None

# in generate(): after `rng = random.Random(seed)`
        noise_rng = (random.Random(seed * 104729 + 1)
                     if regime.promise_error_days or regime.false_promise_rate else None)
        ... return cls(customers=customers, regime=regime, rng=rng, _noise_rng=noise_rng)

# in run_cycle(), replace `tmpl.format(day=c.salary_day)` with:
                            tmpl.format(day=self._promised_day(c.salary_day)),

# new method
    def _promised_day(self, true_day: int) -> int:
        """What the customer SAYS. Draws from a separate stream so noise never
        perturbs failures or reply timing (pinned by tests)."""
        if self._noise_rng is None:
            return true_day
        r = self.regime
        if r.false_promise_rate and self._noise_rng.random() < r.false_promise_rate:
            return self._noise_rng.randint(1, DAYS_PER_MONTH)
        if r.promise_error_days:
            off = self._noise_rng.randint(-r.promise_error_days, r.promise_error_days)
            return (true_day - 1 + off) % DAYS_PER_MONTH + 1
        return true_day
```

- [ ] **Step 5: Run tests, full suite, ruff.** Both new tests pass; the digest test proves the 18 old cells' worlds are unchanged.

- [ ] **Step 6: Commit** — `git commit -am "feat: promise noise knobs on the simulator, old regimes pinned byte-identical"`

---

### Task 4: PromiseAwarePolicy

**Files:**
- Modify: `src/encore/policies.py` (append)
- Modify: `tests/test_policies.py` (append)

**Interfaces:**
- Consumes: `cooldown_aware_start`, `WallConfig`, `day_of_month`, `HOURS_PER_DAY`, `DAYS_PER_MONTH`.
- Produces: `promised_retry_hour(day: int, start_hour: int, max_hour: int | None) -> int | None`; `PromiseAwarePolicy(fallback: Policy, cfg: WallConfig | None = None, max_hour: int | None = None)` with `name = "promise_aware"`, attribute `promises: dict[str, int]`, `propose(failed, state, now_hour)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_policies.py — append (reuse the file's existing _failed/_state helpers and CFG)
from encore.domain import day_of_month
from encore.policies import PromiseAwarePolicy, promised_retry_hour
from encore.wall import decide


def _promise_policy(max_hour=720):
    return PromiseAwarePolicy(FixedSpread10(max_hour=max_hour), max_hour=max_hour)


def test_promised_retry_hour_is_2300_on_the_first_matching_day_at_or_after_start():
    h = promised_retry_hour(25, start_hour=100, max_hour=720)
    assert h == 24 * 24 + 23 and day_of_month(h) == 25
    assert promised_retry_hour(25, start_hour=24 * 24 + 23, max_hour=720) == 24 * 24 + 23
    assert promised_retry_hour(25, start_hour=25 * 24, max_hour=720) is None  # next occurrence is past the window


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
    action = policy.propose(_failed(), _state(retries=1, last_attempt_hour=missed_at), missed_at)
    assert action is not None and action.execute_at_hour >= missed_at + CFG.cooldown_hours
    assert decide(action, _state(retries=1, last_attempt_hour=missed_at), CFG).allowed


def test_promise_aware_stops_at_the_retry_cap():
    policy = _promise_policy()
    policy.promises[_failed().customer_id] = 25
    assert policy.propose(_failed(), _state(retries=CFG.max_retries_per_cycle), 100) is None
```

Check `_state`'s signature in the file first; if it has no `last_attempt_hour` parameter, extend the helper (keyword-only, default `None`).

- [ ] **Step 2: Run to verify failure** — ImportError on `PromiseAwarePolicy`.

- [ ] **Step 3: Implement**

```python
# policies.py — append
def promised_retry_hour(day: int, start_hour: int, max_hour: int | None) -> int | None:
    """23:00 on the first calendar day at or after start_hour whose day-of-month is
    `day`, or None if that hour is not strictly before max_hour. 23:00 is inside
    the wall's 22:00-07:00 window and after the same day's salary credit, which
    the simulator posts at hour 0 of the day."""
    d = start_hour // HOURS_PER_DAY
    last_day = (max_hour // HOURS_PER_DAY) if max_hour is not None else d + DAYS_PER_MONTH
    while d < last_day:
        h = d * HOURS_PER_DAY + 23
        if h >= start_hour and day_of_month(h) == day and (max_hour is None or h < max_hour):
            return h
        d += 1
    return None


class PromiseAwarePolicy:
    """Retries on the day the customer said money arrives; otherwise defers to a
    deterministic fallback. The promise comes from the reply parser (pydantic
    ReplyIntent), which is the only place a language model ever influences
    timing -- and it still never touches legality: every proposal goes through
    wall.decide() like any other. promises is per-run state set by whoever
    parsed the replies (evaluate.run_matrix, agent.RecoveryAgent)."""
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
        # The fallback's failure-anchored schedule has already passed (a missed
        # promise consumed that slot). Re-anchor to the cooldown start at 23:00,
        # keeping the fallback's own spacing, so no retry budget is burnt on a
        # proposal the wall would deny as cooldown_active.
        h = ((start + HOURS_PER_DAY - 1) // HOURS_PER_DAY) * HOURS_PER_DAY + 23
        if h < start:
            h += HOURS_PER_DAY
        if self.max_hour is not None and h >= self.max_hour:
            return None
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, h, state.retries_attempted + 1)
```

Add `from encore.domain import DAYS_PER_MONTH, day_of_month` to the imports.

- [ ] **Step 4: Run tests, full suite, ruff.**

- [ ] **Step 5: Commit** — `git commit -am "feat: promise-aware policy -- the parsed reply picks the day, the wall still picks legality"`

---

### Task 5: Matrix grows to 28 cells; site validator follows; eval rerun

**Files:**
- Modify: `src/encore/evaluate.py` (REGIMES, policy list, promises)
- Modify: `src/encore/webdata.py` (orders)
- Modify: `tests/test_evaluate.py`, `tests/test_webdata.py`
- Modify: `src/encore/cli.py` (`--test-count` default, after the final count is known)

**Interfaces:**
- Consumes: `PromiseAwarePolicy`, `FixedSpread10(max_hour=...)`, `parse_fn -> ReplyIntent`.
- Produces: `REGIMES["r3_noisy_promise"]`; a 7th policy named `promise_aware` in every regime; `eval.json` with 28 cells.

- [ ] **Step 1: Tests**

```python
# tests/test_evaluate.py — append / adjust
def test_matrix_has_28_cells_and_promise_aware_is_present(tmp_path):
    results = run_matrix(seeds=[100], out_dir=tmp_path, n_customers=60)
    assert len(results) == 28
    assert "r3_noisy_promise/promise_aware" in results
    assert all(cell["compliance_violations"] == 0 for cell in results.values())


def test_promises_reach_the_policy_from_parsed_replies(tmp_path, monkeypatch):
    seen = {}
    real = PromiseAwarePolicy.propose

    def spy(self, failed, state, now_hour):
        seen.setdefault("promises", dict(self.promises))
        return real(self, failed, state, now_hour)

    monkeypatch.setattr(PromiseAwarePolicy, "propose", spy)
    run_matrix(seeds=[100], out_dir=tmp_path, n_customers=60)
    assert seen["promises"] and all(1 <= d <= 30 for d in seen["promises"].values())

# tests/test_webdata.py — change the two `== 18` assertions to `== 28`
```

- [ ] **Step 2: Run** — first test fails (18 cells).

- [ ] **Step 3: Implement**

```python
# evaluate.py
REGIMES["r3_noisy_promise"] = RegimeConfig([3, 10, 25], [0.2, 0.3, 0.5], 0.15, 0.12,
                                           promise_error_days=2, false_promise_rate=0.3)
# (write it inside the dict literal, with a comment: r1_shifted's world, customers
#  who are wrong by up to 2 days and lie 30% of the time -- the honesty guard for promise_aware)

# policy list: append
            PromiseAwarePolicy(FixedSpread10(max_hour=EVAL_HORIZON_HOURS),
                               max_hour=EVAL_HORIZON_HOURS),

# next to the kill set, per seed:
                promises = {}
                for r in p.reply_events():
                    intent = parse_fn(r.text)
                    if intent.kind == "promise_to_pay" and intent.promise_day is not None:
                        promises[r.customer_id] = intent.promise_day
                if hasattr(policy, "promises"):
                    policy.promises = promises

# webdata.py
REGIME_ORDER = ["r0_base", "r1_shifted", "r2_no_signal", "r3_noisy_promise"]
POLICY_ORDER = [..., "encore_learned_nopayday", "promise_aware"]
PRECOMPUTED_POLICIES = ["encore_learned", "encore_learned_nopayday", "promise_aware"]
# promise_aware is stdlib but needs the reply parser (pydantic), which is not a
# Tier A module in the browser -- so it is precomputed, not live.
```

Then grep `web/index.template.html` and `src/encore/webhtml.py` for "six", "three regimes", "18" and fix any prose that counts cells.

- [ ] **Step 4: Run tests, full suite, ruff.**

- [ ] **Step 5: Rerun the matrix and the site** (several minutes; not in tests):

```bash
uv run encore eval --seeds 100,101,102 --customers 500
uv run encore report
uv run encore web --test-count <current pytest count>
```

Record `promise_aware` vs `fixed_spread10` and vs `random_in_horizon` on all four regimes in the commit message. Whatever the result, it goes in README §2/§7 in Task 10. If it loses on r1_shifted or r3, that is a BROKELOG entry (design assumption refuted), written before any tuning.

- [ ] **Step 6: Commit** — `git commit -am "feat: promise_aware in the matrix with a noisy-promise regime; 28 cells, site validator updated"`

---

### Task 6: Clock and rails

**Files:**
- Create: `src/encore/clock.py`, `src/encore/rails.py`
- Create: `tests/test_rails.py`

**Interfaces:**
- Produces: `Clock` Protocol (`advance_to(sim_hour: int) -> None`, `monotonic() -> float`, attribute `hour: int`); `InstantClock()`; `SimClock(seconds_per_sim_hour: float, sleep=time.sleep, monotonic=time.monotonic)`; `RailOutcome = Literal["success", "failure", "pending"]`; `AgentRail` Protocol (`name: str`, `execute(action) -> RailOutcome`, `poll(action) -> RailOutcome`, `receipt(action) -> dict`); `SimulatedAgentRail(portfolio)`; `RazorpayLinkRail(client)`.

- [ ] **Step 1: Tests**

```python
# tests/test_rails.py
from encore.clock import InstantClock, SimClock
from encore.domain import ActionKind, ProposedAction, attempt_id
from encore.rails import RazorpayLinkRail, SimulatedAgentRail
from encore.simulator import Portfolio, RegimeConfig

R0 = RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05)


def test_sim_clock_sleeps_proportionally_and_never_goes_backwards():
    slept = []
    clock = SimClock(0.5, sleep=slept.append, monotonic=lambda: 0.0)
    clock.advance_to(10); clock.advance_to(4); clock.advance_to(12)
    assert slept == [5.0, 1.0] and clock.hour == 12


def test_instant_clock_advances_without_sleeping_and_ticks_monotonic():
    clock = InstantClock()
    clock.advance_to(7)
    assert clock.hour == 7 and clock.monotonic() < clock.monotonic()


def test_simulated_rail_maps_debit_to_sync_outcomes():
    p = Portfolio.generate(50, R0, seed=3)
    failures = p.run_cycle(30, "c")
    rail = SimulatedAgentRail(p)
    outcomes = {rail.execute(ProposedAction(ActionKind.RETRY, f.customer_id, "c", f.amount_paise,
                                            f.at_hour + 72, 1)) for f in failures}
    assert outcomes <= {"success", "failure"} and rail.name == "simulated"


class FakeLinks:
    def __init__(self):
        self.created, self.status = [], "created"

    def create_payment_link(self, amount_paise, description, reference_id, notes=None):
        self.created.append((amount_paise, reference_id, notes))
        return {"id": "plink_x", "status": "created", "short_url": "https://rzp.io/x"}

    def fetch_payment_link(self, link_id):
        return {"id": link_id, "status": self.status, "short_url": "https://rzp.io/x"}


def test_link_rail_pends_then_resolves_on_paid():
    fake = FakeLinks()
    rail = RazorpayLinkRail(fake)
    action = ProposedAction(ActionKind.RETRY, "cust_0001", "live", 19900, 95, 1)
    assert rail.execute(action) == "pending"
    assert fake.created[0][1] == attempt_id(action) and fake.created[0][2]["customer_id"] == "cust_0001"
    assert rail.poll(action) == "pending"
    fake.status = "paid"
    assert rail.poll(action) == "success"
    assert rail.receipt(action) == {"link_id": "plink_x", "short_url": "https://rzp.io/x", "status": "paid"}
```

- [ ] **Step 2: Run** — ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# src/encore/clock.py
"""The agent's sense of time, injected so wall.py stays clock-free (CLAUDE.md)."""
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
    def __init__(self, seconds_per_sim_hour: float, sleep=time.sleep, monotonic=time.monotonic) -> None:
        self.hour = 0
        self._spsh, self._sleep, self._monotonic = seconds_per_sim_hour, sleep, monotonic

    def advance_to(self, sim_hour: int) -> None:
        if sim_hour > self.hour:
            self._sleep((sim_hour - self.hour) * self._spsh)
            self.hour = sim_hour

    def monotonic(self) -> float:
        return self._monotonic()
```

```python
# src/encore/rails.py
"""Rails the agent can execute a retry on. The simulated rail answers at once;
the Razorpay rail creates a real test-mode Payment Link and answers "pending"
until a human pays it (or it times out)."""
from typing import Literal, Protocol

from encore.domain import ProposedAction, attempt_id
from encore.scheduler import SimulatedRail
from encore.simulator import Portfolio

RailOutcome = Literal["success", "failure", "pending"]


class AgentRail(Protocol):
    name: str
    def execute(self, action: ProposedAction) -> RailOutcome: ...
    def poll(self, action: ProposedAction) -> RailOutcome: ...
    def receipt(self, action: ProposedAction) -> dict: ...


class SimulatedAgentRail:
    name = "simulated"

    def __init__(self, portfolio: Portfolio) -> None:
        self._rail = SimulatedRail(portfolio)

    def execute(self, action: ProposedAction) -> RailOutcome:
        return "success" if self._rail.execute(action) else "failure"

    def poll(self, action: ProposedAction) -> RailOutcome:
        raise RuntimeError("the simulated rail never pends")

    def receipt(self, action: ProposedAction) -> dict:
        return {}


class RazorpayLinkRail:
    name = "razorpay_test_mode"

    def __init__(self, client) -> None:
        self._client = client
        self._links: dict[str, dict] = {}

    def execute(self, action: ProposedAction) -> RailOutcome:
        aid = attempt_id(action)
        self._links[aid] = self._client.create_payment_link(
            action.amount_paise, f"Encore recovery: {action.customer_id} ({aid})", aid,
            notes={"customer_id": action.customer_id, "cycle_id": action.cycle_id, "attempt_id": aid})
        return "pending"

    def poll(self, action: ProposedAction) -> RailOutcome:
        aid = attempt_id(action)
        link = self._client.fetch_payment_link(self._links[aid]["id"])
        self._links[aid] = link
        if link["status"] == "paid":
            return "success"
        if link["status"] in ("cancelled", "expired"):
            return "failure"
        return "pending"

    def receipt(self, action: ProposedAction) -> dict:
        link = self._links.get(attempt_id(action), {})
        return {"link_id": link.get("id"), "short_url": link.get("short_url"),
                "status": link.get("status")}
```

- [ ] **Step 4: Run tests, full suite, ruff.**

- [ ] **Step 5: Commit** — `git add src/encore/clock.py src/encore/rails.py tests/test_rails.py && git commit -m "feat: injected clock and pending-capable rails for the agent"`

---

### Task 7: The recovery agent loop

**Files:**
- Create: `src/encore/agent.py`
- Create: `tests/test_agent.py`

**Interfaces:**
- Consumes: `decide`, `SequenceState`, `WallConfig` (wall); `Policy` + `PromiseAwarePolicy.promises`; `AgentRail`; `AuditLog`, `AttemptLedger`; `Clock`; `parse_keyword`; `FailedDebit`, `ReplyEvent`, `ProposedAction`, `ActionKind`, `attempt_id`.
- Produces: `RecoveryAgent(wall_cfg, policy, rail, audit, ledger, clock, parse_fn=parse_keyword, live_rail=None, live_customers=frozenset(), poll_interval_s=5.0, timeout_s=180.0, on_tick=None)`; `run(failures: list[FailedDebit], replies: list[ReplyEvent], unmapped: list[dict] = ()) -> AgentResult`; `AgentResult(at_risk_paise, recovered_paise, attempts_executed, attempts_denied, nudges_sent, duplicates_blocked, parked: dict[str, int])`; `records` (in-memory copy of everything appended to the audit). Audit event vocabulary: `nudge`, `reply`, `decision`, `link_created`, `execution`, `park`, `duplicate_blocked`; execution records carry the same keys `scheduler.py` writes plus `rail` and any receipt keys.

- [ ] **Step 1: Tests** (all dry-run, `InstantClock`, simulated rail)

```python
# tests/test_agent.py
from pathlib import Path

from encore.agent import RecoveryAgent
from encore.audit import AttemptLedger, AuditLog
from encore.clock import InstantClock
from encore.domain import DeclineCode, FailedDebit, day_of_month
from encore.policies import FixedSpread10, PromiseAwarePolicy
from encore.rails import SimulatedAgentRail
from encore.simulator import Portfolio, RegimeConfig, ReplyEvent
from encore.wall import WallConfig

R1 = RegimeConfig([3, 10, 25], [0.2, 0.3, 0.5], 0.15, 0.12)


def _world(seed=100, n=120):
    p = Portfolio.generate(n, R1, seed=seed)
    return p, p.run_cycle(30, "agent")


def _agent(tmp_path: Path, p, **kw):
    policy = PromiseAwarePolicy(FixedSpread10(max_hour=720), max_hour=720)
    return RecoveryAgent(WallConfig(), policy, SimulatedAgentRail(p),
                         AuditLog(tmp_path / "a.jsonl"), AttemptLedger(tmp_path / "l.txt"),
                         InstantClock(), **kw), policy


def test_batch_recovers_money_and_every_sequence_ends_in_exactly_one_terminal_event(tmp_path):
    p, failures = _world()
    agent, _ = _agent(tmp_path, p)
    result = agent.run(failures, p.reply_events())
    assert result.recovered_paise > 0 and result.at_risk_paise == sum(f.amount_paise for f in failures)
    wins = sum(1 for r in agent.records if r["event"] == "execution" and r["outcome"] == "success")
    parked = sum(1 for r in agent.records if r["event"] == "park")
    dupes = sum(1 for r in agent.records if r["event"] == "duplicate_blocked")
    assert wins + parked + dupes == len(failures)


def test_hard_declines_are_parked_as_hard_decline_terminal_and_never_executed(tmp_path):
    p, failures = _world()
    hard = {f.customer_id for f in failures if f.decline in
            {DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED, DeclineCode.RISK_DECLINED}}
    agent, _ = _agent(tmp_path, p)
    agent.run(failures, [])
    executed = {r["customer_id"] for r in agent.records if r["event"] == "execution"}
    assert hard and not (hard & executed)
    assert {r["customer_id"] for r in agent.records
            if r["event"] == "park" and r["reason"] == "hard_decline_terminal"} == hard


def test_cancel_reply_kills_the_sequence_before_any_execution(tmp_path):
    p, failures = _world()
    f = next(x for x in failures if x.decline is DeclineCode.INSUFFICIENT_FUNDS)
    agent, _ = _agent(tmp_path, p)
    agent.run([f], [ReplyEvent(f.customer_id, f.at_hour + 2, "cancel karo yeh subscription")])
    assert not [r for r in agent.records if r["event"] == "execution"]
    assert [r["reason"] for r in agent.records if r["event"] == "park"] == ["sequence_killed"]


def test_promise_reply_moves_the_retry_to_the_promised_day(tmp_path):
    p, failures = _world()
    f = next(x for x in failures if x.decline is DeclineCode.INSUFFICIENT_FUNDS and x.at_hour < 5 * 24)
    agent, policy = _agent(tmp_path, p)
    agent.run([f], [ReplyEvent(f.customer_id, f.at_hour + 3, "salary 25 tarikh ko aayegi, tab try karna")])
    assert policy.promises[f.customer_id] == 25
    first = next(r for r in agent.records if r["event"] == "execution")
    assert day_of_month(first["at_hour"]) == 25


def test_dispute_reply_parks_with_reason_dispute(tmp_path):
    p, failures = _world()
    f = next(x for x in failures if x.decline is DeclineCode.INSUFFICIENT_FUNDS)
    agent, _ = _agent(tmp_path, p, parse_fn=lambda text: __import__("encore.parser", fromlist=["ReplyIntent"]).ReplyIntent(kind="dispute"))
    agent.run([f], [ReplyEvent(f.customer_id, f.at_hour + 3, "maine yeh kabhi liya hi nahi")])
    assert [r["reason"] for r in agent.records if r["event"] == "park"] == ["dispute"]


def test_unmapped_failures_are_parked_and_counted_at_risk(tmp_path):
    p, failures = _world()
    agent, _ = _agent(tmp_path, p)
    result = agent.run([], [], unmapped=[{"payment_id": "pay_9", "customer_id": "rzp:pay_9",
                                         "error_reason": "card_declined", "amount_paise": 49900}])
    assert result.parked == {"unmapped_error_reason": 1} and result.at_risk_paise == 49900


def test_rerun_with_the_same_ledger_executes_nothing_new(tmp_path):
    p, failures = _world()
    agent, _ = _agent(tmp_path, p)
    first = agent.run(failures, [])
    p2, failures2 = _world()
    agent2, _ = _agent(tmp_path, p2)
    second = agent2.run(failures2, [])
    assert first.attempts_executed > 0 and second.attempts_executed == 0
    assert second.duplicates_blocked > 0


def test_nudge_is_sent_once_per_failure_and_gated_by_the_wall(tmp_path):
    p, failures = _world()
    agent, _ = _agent(tmp_path, p)
    result = agent.run(failures, [])
    assert result.nudges_sent == len(failures)
```

- [ ] **Step 2: Run** — ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# src/encore/agent.py
"""The live recovery loop. Not Scheduler.run: that is the synchronous batch
evaluator behind the 28-cell matrix. This loop interleaves a clock, customer
replies, wall decisions and rails that may answer "pending". Every legality
question still goes to wall.decide(); every attempt still goes through the
same AttemptLedger; every event is appended to the same AuditLog shape."""
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from encore.audit import AttemptLedger, AuditLog
from encore.clock import Clock
from encore.domain import ActionKind, FailedDebit, ProposedAction, attempt_id
from encore.parser import ReplyIntent, parse_keyword
from encore.policies import Policy
from encore.rails import AgentRail
from encore.simulator import ReplyEvent
from encore.wall import SequenceState, WallConfig, decide

TERMINAL_DENIALS = ("hard_decline_terminal", "sequence_killed", "retry_cap_exceeded")


@dataclass
class AgentResult:
    at_risk_paise: int = 0
    recovered_paise: int = 0
    attempts_executed: int = 0
    attempts_denied: int = 0
    nudges_sent: int = 0
    duplicates_blocked: int = 0
    parked: dict[str, int] = field(default_factory=dict)


@dataclass
class _Seq:
    failed: FailedDebit
    state: SequenceState
    started: bool = False
    next_action: ProposedAction | None = None
    pending: ProposedAction | None = None
    pending_since: float | None = None
    last_poll: float | None = None
    done: bool = False


class RecoveryAgent:
    def __init__(self, wall_cfg: WallConfig, policy: Policy, rail: AgentRail, audit: AuditLog,
                 ledger: AttemptLedger, clock: Clock,
                 parse_fn: Callable[[str], ReplyIntent] = parse_keyword,
                 live_rail: AgentRail | None = None, live_customers: frozenset[str] = frozenset(),
                 poll_interval_s: float = 5.0, timeout_s: float = 180.0,
                 on_tick: Callable[["RecoveryAgent", AgentResult], None] | None = None) -> None:
        self.cfg, self.policy, self.rail, self.audit, self.ledger, self.clock = (
            wall_cfg, policy, rail, audit, ledger, clock)
        self.parse_fn, self.live_rail, self.live_customers = parse_fn, live_rail, live_customers
        self.poll_interval_s, self.timeout_s, self.on_tick = poll_interval_s, timeout_s, on_tick
        self.records: list[dict] = []
        self.result = AgentResult()

    # -- audit -------------------------------------------------------------
    def _log(self, record: dict) -> None:
        self.audit.append(record)
        self.records.append(record)

    def _rail_for(self, customer_id: str) -> AgentRail:
        if self.live_rail is not None and customer_id in self.live_customers:
            return self.live_rail
        return self.rail

    def _park(self, s: _Seq, reason: str) -> None:
        s.done, s.next_action = True, None
        self.result.parked[reason] = self.result.parked.get(reason, 0) + 1
        self._log({"event": "park", "customer_id": s.failed.customer_id,
                   "cycle_id": s.failed.cycle_id, "reason": reason, "policy": self.policy.name})

    # -- the loop ----------------------------------------------------------
    def run(self, failures: list[FailedDebit], replies: list[ReplyEvent],
            unmapped: list[dict] = ()) -> AgentResult:
        result = self.result
        result.at_risk_paise = sum(f.amount_paise for f in failures) + \
            sum(u["amount_paise"] for u in unmapped)
        for u in unmapped:
            result.parked["unmapped_error_reason"] = result.parked.get("unmapped_error_reason", 0) + 1
            self._log({"event": "park", "customer_id": u["customer_id"], "reason": "unmapped_error_reason",
                       "error_reason": u["error_reason"], "payment_id": u["payment_id"],
                       "amount_paise": u["amount_paise"], "policy": self.policy.name})
        seqs = {f.customer_id: _Seq(f, SequenceState(f.decline, 0, 0, None, False)) for f in failures}
        replies = sorted(replies, key=lambda r: r.at_hour)
        ri = 0
        now = min((f.at_hour for f in failures), default=0)
        while True:
            self.clock.advance_to(now)
            while ri < len(replies) and replies[ri].at_hour <= now:
                self._handle_reply(seqs, replies[ri], now)
                ri += 1
            for s in seqs.values():
                if not s.done and not s.started and s.failed.at_hour <= now:
                    self._start(s, now)
            for s in seqs.values():
                if not s.done and s.pending is None and s.next_action is not None \
                        and s.next_action.execute_at_hour <= now:
                    self._execute(s, now)
            for s in seqs.values():
                if s.pending is not None:
                    self._poll(s, now)
            if self.on_tick:
                self.on_tick(self, result)
            if all(s.done for s in seqs.values()):
                return result
            due = [s.next_action.execute_at_hour for s in seqs.values()
                   if not s.done and s.pending is None and s.next_action is not None]
            due += [s.failed.at_hour for s in seqs.values() if not s.started]
            if ri < len(replies):
                due.append(replies[ri].at_hour)
            if any(s.pending is not None for s in seqs.values()):
                now += 1  # a live link is waiting on a human: creep one sim hour per poll
            elif due:
                now = max(now, min(due))
            else:
                return result

    # -- steps -------------------------------------------------------------
    def _start(self, s: _Seq, now: int) -> None:
        s.started = True
        nudge = ProposedAction(ActionKind.NUDGE, s.failed.customer_id, s.failed.cycle_id,
                               s.failed.amount_paise, now, 1)
        d = decide(nudge, s.state, self.cfg)
        self._log({"event": "decision", "customer_id": nudge.customer_id, "attempt_id": attempt_id(nudge),
                   "kind": str(nudge.kind), "at_hour": now, "allowed": d.allowed, "reason": d.reason,
                   "policy": self.policy.name})
        if d.allowed:
            self.result.nudges_sent += 1
            s.state = replace(s.state, nudges_sent=s.state.nudges_sent + 1)
            self._log({"event": "nudge", "customer_id": nudge.customer_id,
                       "attempt_id": attempt_id(nudge), "at_hour": now})
        self._plan(s, now)

    def _plan(self, s: _Seq, now: int) -> None:
        """Propose until the wall allows one, exactly as Scheduler.run does:
        non-terminal denials burn budget; terminal denials park the sequence."""
        while not s.done:
            base = max(now, s.state.last_attempt_hour or s.failed.at_hour)
            action = self.policy.propose(s.failed, s.state, base)
            if action is None:
                self._park(s, "policy_stop")
                return
            d = decide(action, s.state, self.cfg)
            self._log({"event": "decision", "customer_id": action.customer_id,
                       "attempt_id": attempt_id(action), "kind": str(action.kind),
                       "at_hour": action.execute_at_hour, "allowed": d.allowed, "reason": d.reason,
                       "policy": self.policy.name})
            if d.allowed:
                s.next_action = action
                return
            self.result.attempts_denied += 1
            if d.reason in TERMINAL_DENIALS:
                self._park(s, d.reason)
                return
            s.state = replace(s.state, retries_attempted=s.state.retries_attempted + 1,
                              last_attempt_hour=action.execute_at_hour)

    def _execute(self, s: _Seq, now: int) -> None:
        action = s.next_action
        aid = attempt_id(action)
        s.next_action = None
        if self.ledger.already_executed(aid):
            self.result.duplicates_blocked += 1
            self._log({"event": "duplicate_blocked", "attempt_id": aid, "customer_id": action.customer_id})
            s.done = True
            return
        self.ledger.record(aid)
        rail = self._rail_for(action.customer_id)
        outcome = rail.execute(action)
        if outcome == "pending":
            s.pending, s.pending_since, s.last_poll = action, self.clock.monotonic(), None
            self._log({"event": "link_created", "customer_id": action.customer_id, "attempt_id": aid,
                       "at_hour": action.execute_at_hour, "amount_paise": action.amount_paise,
                       "rail": rail.name, **rail.receipt(action)})
            return
        self._resolve(s, action, outcome, rail, now)

    def _poll(self, s: _Seq, now: int) -> None:
        rail = self._rail_for(s.failed.customer_id)
        t = self.clock.monotonic()
        if s.last_poll is not None and t - s.last_poll < self.poll_interval_s:
            return
        s.last_poll = t
        outcome = rail.poll(s.pending)
        if outcome == "pending":
            if t - s.pending_since >= self.timeout_s:
                self._resolve(s, s.pending, "failure", rail, now, status="no_terminal_status_within_timeout")
            return
        self._resolve(s, s.pending, outcome, rail, now)

    def _resolve(self, s: _Seq, action: ProposedAction, outcome: str, rail: AgentRail, now: int,
                 status: str | None = None) -> None:
        s.pending = None
        self.result.attempts_executed += 1
        record = {"event": "execution", "customer_id": action.customer_id, "attempt_id": attempt_id(action),
                  "at_hour": action.execute_at_hour, "outcome": outcome,
                  "amount_paise": action.amount_paise, "policy": self.policy.name,
                  "original_decline": str(s.state.original_decline), "attempt_no": action.attempt_no,
                  "rail": rail.name, **rail.receipt(action)}
        if status:
            record["status"] = status
        self._log(record)
        if outcome == "success":
            self.result.recovered_paise += action.amount_paise
            s.done = True
            return
        s.state = replace(s.state, retries_attempted=s.state.retries_attempted + 1,
                          last_attempt_hour=action.execute_at_hour)
        self._plan(s, max(now, action.execute_at_hour))

    def _handle_reply(self, seqs: dict[str, _Seq], reply: ReplyEvent, now: int) -> None:
        intent = self.parse_fn(reply.text)
        self._log({"event": "reply", "customer_id": reply.customer_id, "at_hour": reply.at_hour,
                   "text": reply.text, "kind": intent.kind, "promise_day": intent.promise_day})
        s = seqs.get(reply.customer_id)
        if s is None or s.done:
            return
        if intent.kind == "cancel":
            s.state = replace(s.state, killed=True)
            if s.pending is None:
                s.next_action = None
                self._plan(s, now)  # the wall now answers sequence_killed -> park
        elif intent.kind == "dispute":
            if s.pending is None:
                self._park(s, "dispute")
        elif intent.kind == "promise_to_pay" and intent.promise_day is not None \
                and hasattr(self.policy, "promises"):
            self.policy.promises[reply.customer_id] = intent.promise_day
            if s.started and s.pending is None and not s.done:
                s.next_action = None
                self._plan(s, now)
```

Note on replies before `_start`: a reply whose `at_hour` precedes the failure hour cannot happen (replies are generated 4–48 h after failure). A promise arriving before the sequence has started simply sets `policy.promises`; `_start` then plans with it.

- [ ] **Step 4: Run tests, full suite, ruff.** Expect all 8 new tests green. If a test fails for a reason not predicted here, BROKELOG first.

- [ ] **Step 5: Commit** — `git add src/encore/agent.py tests/test_agent.py && git commit -m "feat: recovery agent loop -- replies, wall decisions, rails and a clock, same audit shape"`

---

### Task 8: The board

**Files:**
- Create: `src/encore/board.py`, `tests/test_board.py`

**Interfaces:**
- Consumes: `report.format_rupees`, `report._esc`.
- Produces: `build_board(records: list[dict], at_risk_by_customer: dict[str, int]) -> dict` with keys `at_risk_paise, recovered_paise, in_flight, attempts, nudges, replies, denials: dict, parked: dict, customers: list[dict]` (each `customer_id, amount_paise, rail, last_event, link_id, short_url, status`); `render_board(data: dict, provenance: str, refresh_s: int = 3) -> str`; `write_board(path: Path, data: dict, provenance: str) -> None`.

- [ ] **Step 1: Tests**

```python
# tests/test_board.py
from pathlib import Path

from encore.board import build_board, render_board, write_board

RECORDS = [
    {"event": "nudge", "customer_id": "c1", "attempt_id": "c1:x:nudge:1", "at_hour": 10},
    {"event": "reply", "customer_id": "c1", "at_hour": 12, "text": "salary 25 tarikh", "kind": "promise_to_pay", "promise_day": 25},
    {"event": "decision", "customer_id": "c1", "attempt_id": "c1:x:retry:1", "kind": "retry", "at_hour": 599, "allowed": True, "reason": "ok", "policy": "promise_aware"},
    {"event": "link_created", "customer_id": "c1", "attempt_id": "c1:x:retry:1", "at_hour": 599, "amount_paise": 19900, "rail": "razorpay_test_mode", "link_id": "plink_1", "short_url": "https://rzp.io/1", "status": "created"},
    {"event": "decision", "customer_id": "c2", "attempt_id": "c2:x:retry:1", "kind": "retry", "at_hour": 30, "allowed": False, "reason": "hard_decline_terminal", "policy": "promise_aware"},
    {"event": "park", "customer_id": "c2", "reason": "hard_decline_terminal", "policy": "promise_aware"},
    {"event": "execution", "customer_id": "c3", "attempt_id": "c3:x:retry:1", "at_hour": 95, "outcome": "success", "amount_paise": 29900, "policy": "promise_aware", "original_decline": "insufficient_funds", "attempt_no": 1, "rail": "simulated"},
]
AT_RISK = {"c1": 19900, "c2": 49900, "c3": 29900}


def test_build_board_totals_and_exceptions():
    b = build_board(RECORDS, AT_RISK)
    assert b["at_risk_paise"] == 99700 and b["recovered_paise"] == 29900
    assert b["in_flight"] == 1 and b["attempts"] == 1 and b["nudges"] == 1 and b["replies"] == 1
    assert b["denials"] == {"hard_decline_terminal": 1} and b["parked"] == {"hard_decline_terminal": 1}
    rows = {c["customer_id"]: c for c in b["customers"]}
    assert rows["c1"]["link_id"] == "plink_1" and rows["c1"]["last_event"] == "link_created"
    assert rows["c3"]["last_event"] == "recovered" and rows["c2"]["last_event"] == "parked: hard_decline_terminal"


def test_render_board_is_html_with_rupees_and_refresh(tmp_path: Path):
    html = render_board(build_board(RECORDS, AT_RISK), "seed 100, r1_shifted")
    assert "₹299.00" in html and "₹997.00" in html and 'http-equiv="refresh"' in html
    assert "plink_1" in html and "hard_decline_terminal" in html and "seed 100" in html
    write_board(tmp_path / "board.html", build_board(RECORDS, AT_RISK), "p")
    assert (tmp_path / "board.html").read_text(encoding="utf-8").startswith("<!doctype html>")
```

- [ ] **Step 2: Run** — ModuleNotFoundError.

- [ ] **Step 3: Implement** — `build_board` folds records in order: track per-customer last event (`nudged`, `replied: <kind>`, `scheduled`, `link_created`, `recovered`, `failed attempt n`, `parked: <reason>`, `duplicate_blocked`), rail, link fields; totals from `execution`/`park`/`decision(allowed=False)`/`nudge`/`reply`; `in_flight` = `link_created` attempt_ids without a later `execution`. `render_board` is one f-string page: four stat cards (`format_rupees` for money), two small tables (denials, parked), the customer table, and `<meta http-equiv="refresh" content="{refresh_s}">`; escape every string with `report._esc`; no JS, no external CSS (a 20-line inline `<style>` using the site's tokens: `#FCF8F9` surface, `#00205B` navy, IBM Plex fallbacks to system fonts). `write_board` writes to a temp file then `os.replace` so a browser refresh never reads a half-written page.

- [ ] **Step 4: Run tests, full suite, ruff.**

- [ ] **Step 5: Commit** — `git add src/encore/board.py tests/test_board.py && git commit -m "feat: live recovery board -- pure transform over the audit log, static HTML, no JS"`

---

### Task 9: CLI `seed-live` and `agent`; dry-run and live rehearsal

**Files:**
- Modify: `src/encore/cli.py`
- Modify: `docs/spike-notes.md` (rehearsal transcript)

**Interfaces:**
- Produces: `encore seed-live --n 3 [--seed 100 --regime r1_shifted]` → creates N original links (notes `customer_id`, `cycle_id="live"`, `reference_id=f"{cid}:live:original:{unix}"`) for the first N insufficient-funds failures of the seeded world, prints URLs, writes `runs/live_originals.json` (`[{customer_id, amount_paise, link_id, order_id, short_url}]`). `encore agent --batch 50 --live 0 --seed 100 --regime r1_shifted --customers 500 --speed 2 --interval 5 --timeout 180 [--dry-run]` → runs `RecoveryAgent`, board at `runs/board.html`, audit `runs/agent_audit.jsonl`, ledger `runs/agent_ledger.txt` (`_dryrun` suffix in dry run), prints a summary. `--speed` = simulated hours per real second. `--dry-run` forces `--live 0`.

- [ ] **Step 1: Implement `cmd_seed_live` and `cmd_agent`** following `cmd_demo`'s shape. In `cmd_agent`: world = `Portfolio.generate(customers, REGIMES[regime], seed)`; `failures = SimulatedFailureSource(world, f"agent_s{seed}").failures()[:batch]`; `replies = [r for r in world.reply_events() if r.customer_id in batch_ids]`; if `live > 0`: `load_dotenv()`, `client = RazorpayClient()`, `anchor = IST midnight today` (compute `now - ((now + IST_OFFSET_S) % 86400)`), `src = RazorpayFailureSource(client, now - 3 * 3600, now, "live", anchor)`, `live_failures = src.failures()[:live]`, `live_customers = {f.customer_id for f in live_failures}`, `live_rail = RazorpayLinkRail(client)`; policy = `PromiseAwarePolicy(FixedSpread10(max_hour=EVAL_HORIZON_HOURS), max_hour=EVAL_HORIZON_HOURS)`; clock = `SimClock(1 / speed)`; `on_tick` writes the board with `build_board(agent.records, at_risk_by_customer)` and a provenance line naming seed, regime, batch, live count, rails. Print the `AgentResult` fields and the parked breakdown at the end.

- [ ] **Step 2: Dry run**

```bash
rm -f runs/agent_ledger_dryrun.txt runs/agent_audit_dryrun.jsonl
uv run encore agent --dry-run --batch 50 --speed 200
```

Expected: summary with at_risk > 0, recovered > 0, parked reasons listed; `runs/board.html` opens and shows ≥ 50 customers. Re-run without deleting the ledger → `attempts_executed 0`, duplicates > 0.

- [ ] **Step 3: Live rehearsal** (operator present; check the dashboard link count first):

```bash
uv run encore seed-live --n 2
```

Fail both printed links on checkout with `4100 2800 0008 0001`. Then:

```bash
rm -f runs/agent_ledger.txt runs/agent_audit.jsonl
PYTHONUNBUFFERED=1 uv run encore agent --batch 50 --live 2 --speed 2 --timeout 240
```

Expected: the two live customers are detected with `insufficient_funds`, nudged, and at T+3 23:00 (≈ 36 s at speed 2 from a hour-14 failure) a real recovery link is printed via the board / stdout; pay one on the Netbanking mock bank → `paid` → recovered; let the other time out → `no_terminal_status_within_timeout`. Paste the transcript and a board screenshot path into `docs/spike-notes.md`.

- [ ] **Step 4: Full suite, ruff, commit** — `git commit -am "feat: encore agent and seed-live -- the loop runs on the real rail for a live slice and the simulator for the batch"`

---

### Task 10: Evidence, docs, video, form

**Files:**
- Modify: `README.md`, `docs/what-broke-essay.md`, `docs/demo-script.md`, `docs/submission-checklist.md`, `CLAUDE.md`, `AGENTS.md`, `BROKELOG.md` (only new entries), `src/encore/cli.py` (`--test-count` default)

- [ ] **Step 1: `uv run encore parse-eval`** with `ANTHROPIC_API_KEY` in `.env` if available. Paste the printed rows into README §5's table verbatim; if no key, the rows stay "not yet measured".
- [ ] **Step 2: README** — new first paragraph: what the agent does in one breath (detects failed debits from the Payments API, nudges, reads the reply, retries inside the NPCI-shaped wall, collects on a real Payment Link, shows rupees recovered). New §2 rows for `promise_aware` and `r3_noisy_promise`, pasted from `runs/eval.json`. Tagline quotes the wide-horizon result and states the model ties random in-distribution (0.99x) and loses under shift. Board screenshot under a new "§4 The agent, live" with the rehearsal's real `plink_`/`pay_` ids. §7 keeps every caveat; add: simulated replies, 30-link cap, no UPI in test mode, promise accuracy is a simulator knob. Replace "seven entries"/"ten entries" with the current count. `AGENTS.md` repo map: add `sources.py`, `clock.py`, `rails.py`, `agent.py`, `board.py`, the two new commands.
- [ ] **Step 3: `CLAUDE.md`** — delete the line `Every public repo commit message is written for a judge's eyes.`
- [ ] **Step 4: Essay** — add sections for entries 11, 12 and this build's entries; keep the closing.
- [ ] **Step 5: Demo script** — beats: (1) problem 20 s; (2) `encore seed-live --n 1` + fail on checkout 40 s; (3) `encore agent --live 1 --batch 50` and the board filling 90 s; (4) pay the recovery link, watch `recovered` move 40 s; (5) the wall + the control experiment as the honest close 60 s; (6) BROKELOG 20 s. Time each; total under 4:55.
- [ ] **Step 6: `--test-count` default** in `cli.py` set to the final `pytest` count; `uv run encore web` rebuilt.
- [ ] **Step 7: Full suite, ruff, commit, push** — `git push -u origin claude/buildathon-project-strategy-71f7cb`, open the PR to main, merge, rerun `encore eval` on main only if `runs/` is regenerated there.
- [ ] **Step 8: Record the video; fill the form; submit.**

---

## Self-review

- Spec coverage: detection (T1–T2), promise policy + noise (T3–T5), agent + rails + clock (T6–T7), board (T8), CLI + live (T9), docs/video/form (T10). Subscriptions stretch: intentionally absent.
- Types: `RailOutcome` strings match between rails.py and agent.py; `AgentResult.parked` is `dict[str, int]` everywhere; `promises: dict[str, int]` in policy, evaluate, agent; `FailedDebit` positional order `(customer_id, cycle_id, amount_paise, decline, at_hour)` used consistently.
- Placeholders: only `PINNED = "<hex from Step 1>"`, which Task 3 Step 1 fills by running the command.
