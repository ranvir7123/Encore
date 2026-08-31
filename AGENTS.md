# AGENTS.md

Written for whoever (human or agent) picks this repo up next. See
`README.md` for the measured results and honest limitations; this file is
the map and the rulebook, not the pitch.

## Repo map

| Path | What it is |
|---|---|
| `src/encore/domain.py` | Core value types: `DeclineCode`, `HARD_DECLINES`, `FailedDebit`, `ProposedAction`, `attempt_id()`; `DAYS_PER_MONTH = 30`, `HOURS_PER_DAY = 24`. No logic beyond these — every other module imports from here. |
| `src/encore/simulator.py` | `Portfolio`: seeded, latent-state customer simulation — balances, salary credits, issuer-down windows, hard/soft declines, reply generation. `would_succeed()` (labeling oracle) and `debit()` (mechanical rail) are both time-aware via `balance_history`, deliberately diverge on `churn_intent` — see README limitations. |
| `src/encore/wall.py` | `decide()`: the pure compliance gate. No I/O, no clock, no randomness — everything it needs is a parameter. This is the one file that must never change to "make a metric look better." |
| `src/encore/policies.py` | `ImmediateRetry3` (deliberately dumb baseline), `FixedSchedule` (Razorpay's documented T+1/T+2/T+3, our real baseline), and the `Policy` protocol. |
| `src/encore/model.py` | `LearnedPolicy`: HistGradientBoostingClassifier over hand-built features (`featurize()`), `generate_training_data()`, `train()`. Stopping rule is one comparison (`probs[best] * amount < cost`), not a model. |
| `src/encore/scheduler.py` | `Scheduler.run()`: drives a policy against the wall, the audit log, and a rail (real or simulated) for one portfolio of failures. `SimulatedRail` wraps `Portfolio.debit`. |
| `src/encore/audit.py` | `AuditLog` (append-only JSONL) and `AttemptLedger` (crash-safe idempotency: `already_executed()` / `record()`). |
| `src/encore/parser.py` | `parse_keyword()` (regex, default, money-adjacent path), `parse_llm()` (Claude, always falls back to `parse_keyword` on any failure — see the `noqa: BLE001` on its broad except), `evaluate()` (scores a parser against a labeled JSONL set). Everything routes through the pydantic `ReplyIntent` model. |
| `src/encore/evaluate.py` | `REGIMES` (the three regime configs), `TRAIN_SEEDS`/`EVAL_SEED_FLOOR`, `run_matrix()` (the eval harness — writes `runs/eval.json`), `count_violations()` (post-hoc wall-violation checker). **Seeds and regimes live here.** |
| `src/encore/razorpay_client.py` | Thin `httpx` wrapper over the Razorpay Payment Links API (`create_payment_link`, `fetch_payment_link`) plus `poll_until_terminal()`. `TERMINAL_STATUSES = {"paid", "cancelled", "expired"}` — deliberately excludes "failed"; see the module docstring and `docs/spike-notes.md`. |
| `src/encore/demo.py` | `run_demo_slice()`: Task 11's real-rail proof — takes real soft-decline failures from a seeded `Portfolio`, creates genuine Razorpay test-mode Payment Links, polls them, writes the same audit-log shape the simulator writes. `--dry-run` runs the identical code path against `SimulatedRail` instead. |
| `src/encore/report.py` | `format_rupees()` (integer paise → `₹` string, Indian digit grouping — the only place a paise integer becomes a display string), `render()`/`write_scoreboard()` (builds `runs/scoreboard.html` from `runs/eval.json`, plain f-strings, no template engine). |
| `src/encore/cli.py` | `encore` entry point (`pyproject.toml`: `encore = "encore.cli:main"`). Four subcommands: `eval`, `report`, `parse-eval`, `demo`. |
| `scripts/spike.py` | Task 2's original Razorpay Payment Links spike script (create + fetch a link). Historical, not part of the pipeline. |
| `data/reply_eval.jsonl` | 40-row hand-labeled `{text, kind, promise_day}` set the parser is scored against. |
| `runs/` | Gitignored. `eval.json`, `scoreboard.html`, per-cell audit/ledger files, demo artifacts. Regenerate with `encore eval` / `encore report` / `encore demo`; nothing here is committed. |
| `tests/` | One file per `src/encore/*` module (`test_domain.py`, `test_simulator.py`, `test_wall.py`, `test_scheduler.py`, `test_model.py`, `test_parser.py`, `test_audit.py`, `test_evaluate.py`, `test_report.py`). |
| `BROKELOG.md` | Append-only record of every unpredicted test failure, bug in believed-done code, reversed design decision, or API surprise, with root cause and fix commit. Never edited after the fact. Read it before assuming a limitation in README is unexplained — it probably has an entry. |
| `docs/spike-notes.md` | Ground truth for Razorpay test-mode reality: no UPI on this account's checkout, Netbanking's mock bank page substitutes, a failed attempt never moves a Payment Link's `status` off `created`. |
| `CLAUDE.md` | The project rules this file restates below, plus the broke-log entry format and the verification rule. |

## Commands

All commands assume `uv sync` has been run (installs from `pyproject.toml` /
`uv.lock`, Python `>=3.13`).

```bash
uv run pytest -q               # full suite
uv run pytest -q tests/test_wall.py   # one module
uv run ruff check .            # lint (line-length=100, py313 target)
```

```bash
uv run encore eval [--seeds 100,101,102] [--customers 500] [--out-dir runs]
# runs REGIMES x [ImmediateRetry3, FixedSchedule, LearnedPolicy] over the
# given seeds, trains LearnedPolicy once on r0_base/TRAIN_SEEDS, writes
# <out-dir>/eval.json plus one audit+ledger file pair per (regime, policy, seed).

uv run encore report [--eval-path runs/eval.json] [--out-path runs/scoreboard.html] [--audit-dir runs]
# reads eval.json, writes the static HTML scoreboard (table + denial
# breakdown + one sample audit trail).

uv run encore parse-eval [--eval-path data/reply_eval.jsonl]
# scores parse_keyword, then claude-haiku-4-5 and claude-sonnet-5 if
# ANTHROPIC_API_KEY is set (loaded from .env via load_dotenv()); prints only
# what it actually measured, never fabricates the LLM rows if the key is missing.

uv run encore demo [--n 3] [--timeout 300] [--dry-run]
# Task 11's live-rail proof. Without --dry-run, needs RAZORPAY_KEY_ID /
# RAZORPAY_KEY_SECRET in .env and creates real (test-mode) Payment Links --
# each reference_id is consumed forever on the account, see docs/spike-notes.md.
# --dry-run runs the identical path against SimulatedRail, no network.
```

Copy `.env.example` to `.env` and fill in `RAZORPAY_KEY_ID`,
`RAZORPAY_KEY_SECRET`, and (optionally, only needed for `parse-eval`'s LLM
rows and `demo`'s non-dry-run mode) `ANTHROPIC_API_KEY`. `.env` is
gitignored — never commit it.

## Seeds and regimes

Both live in `src/encore/evaluate.py`:

- `REGIMES: dict[str, RegimeConfig]` — `r0_base`, `r1_shifted`, `r2_no_signal`.
  Read the module docstring comment above `REGIMES` for what each one
  changes and why.
- `TRAIN_SEEDS = [1, 2, 3, 4, 5]` — the only seeds `LearnedPolicy` is ever
  trained on, always against `r0_base`. Never reused for eval.
- `EVAL_SEED_FLOOR = 100` — eval seeds start here (`100, 101, 102` by
  default) and are disjoint from `TRAIN_SEEDS` by construction (100 > 5).
  `demo.py` reuses `EVAL_SEED_FLOOR` itself as `DEMO_SEED` rather than
  inventing a new seed, so every non-training run in the repo draws from
  the same documented range.
- `evaluate.py::run_matrix`'s own docstring explains the `cycle_id`
  strategy (`run_cycle(30, ...)` — one billing period per seed, plus a
  per-seed `cycle_id` of `f"eval_s{seed}"`) that avoids the double-billing
  collision documented in `BROKELOG.md`'s second entry.

## Non-negotiables (restated from `CLAUDE.md`)

- **Money is integer paise everywhere.** A float representing an amount,
  anywhere, is a bug. `format_rupees()` in `report.py` is the one and only
  place a paise integer becomes a display string, and it happens last.
- **`wall.py` stays pure.** No I/O, no clock, no randomness, no LLM call.
  Everything `decide()` needs comes in as a parameter. If a check needs a
  clock or a call, that's a sign it belongs in the caller, not the wall.
- **No LLM call on the money path.** The wall, the scheduler, the rail, and
  the stopping rule are all deterministic arithmetic/logic. The only LLM
  call in the codebase (`parser.py::parse_llm`) produces a pydantic-
  validated `ReplyIntent` from a customer reply, and that output can only
  ever add a `customer_id` to the wall's kill set — never propose an
  amount, an hour, or a retry, and it never touches the rail.
- **All randomness is seeded and explicit.** Every `random.Random` instance
  is constructed from an explicit seed and passed in; nothing reaches for
  the global `random` module. `test_same_seed_same_world` /
  `test_different_seed_different_world` in `tests/test_simulator.py` pin
  this.
- **The audit log is append-only.** `AuditLog.append()` only ever opens in
  `"a"` mode; nothing in the codebase rewrites or truncates
  `runs/*_audit.jsonl`. `AttemptLedger` is the crash-safe idempotency
  companion — `already_executed()` before `record()`, always.
- **Run `uv run pytest -q` and `uv run ruff check .` before every commit.**
  Both must pass clean. If a test fails for a reason you did not predict,
  append a `BROKELOG.md` entry (see `CLAUDE.md` for the exact format)
  *before* fixing it, not after.
