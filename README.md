# Encore

Compliance-first retry sequencer for failed UPI AutoPay / card e-mandate
debits. A pure-function wall decides **whether** a retry is legal; a policy
chooses **when**, inside it — never the other way around. Recovers **2.85x
the industry-standard T+1/T+2/T+3 schedule** across three regimes with
**zero compliance violations in all 18 evaluated cells**.

> **Read §7 before you read the metrics table.** We built a horizon-matched
> control — the same retry budget, the same candidate hours, chosen at
> random instead of by the model — and on the held-out regime **it beats our
> trained model by 47%**. We then tested our own explanation for why, and
> that was wrong too. Both results are in `BROKELOG.md` (entries 9 and 10),
> written before either fix. The wall is the part of this system that works;
> the ML is not, and we would rather you heard that from us.

## 1. The problem

UPI AutoPay mandates fail to execute at a rate that would be a P0 outage in
any other payments system, and merchants have almost no compliant room to
react. NPCI data reported by Business Standard puts UPI AutoPay revocations
at **20M+ mandates cancelled per month**, mostly over low customer balances
([Business Standard, Sept 2025](https://www.business-standard.com/finance/news/upi-autopay-revocations-hit-20-mn-monthly-over-low-customer-balances-125090700500_1.html)).
NPCI data reported via Mint puts the **August 2025 AutoPay execution failure
rate at 55–90%** across public and private banks in a single month
([Mint, via HT Syndication](https://www.htsyndication.com/mint/article/upi-autopay-s-recurring-woes-are-forcing-an-industry-rethink/93925664)).
Even in steady state, UPI AutoPay's structural failure rate — one bank
authorization per debit, no persistent card-network token — sits at a
reported **8–15%, versus 2–3% for card mandates**
([productgrowth.in AutoPay guide](https://productgrowth.in/insights/fintech/upi-autopay-guide/)).
Every one of those failures is a subscription that silently churns unless
someone retries it — and NPCI's own rules constrain how: **one original
execution plus three retries, only in non-peak windows**
([Paytm, on NPCI's Aug-2025 UPI rules](https://paytm.com/blog/payments/upi/upi-rules-update-august-1-npci-new-guidelines/)).
Encore is a policy layer for that narrow, rule-bound retry budget: recover
what NPCI's own retry allowance permits, and refuse everything it doesn't —
never the reverse.

## 2. The metrics table

Pasted verbatim from `runs/eval.json`, the real output of
`uv run encore eval` — seeds `[100, 101, 102]`, `n_customers=500` per seed.
Both learned models are trained once on regime `r0_base`, seeds `1`–`5`
only (never on an eval seed). Money is in ₹, Indian digit grouping, exactly
as `encore report` renders it on `runs/scoreboard.html`.

**Read the `random_in_horizon` row before the `encore_learned` row.** It is
the control that decides what this table actually shows, and on two of three
regimes it wins. See §7.

| Regime | Policy | Recovered / 1000 failures | Recovery / attempt | Max contacts / customer | Parked | Violations |
|---|---|---:|---:|---:|---:|---:|
| r0_base | `immediate_x3` | ₹0.00 | ₹0.00 | 0 | ₹41,417.00 | 0 |
| r0_base | `fixed_t123` | ₹68,040.91 | ₹70.61 | 3 | ₹26,448.00 | 0 |
| r0_base | `fixed_spread10` | ₹1,65,581.82 | ₹241.25 | 3 | ₹4,989.00 | 0 |
| r0_base | `random_in_horizon` | ₹1,82,359.09 | ₹331.56 | 3 | ₹1,298.00 | 0 |
| r0_base | `encore_learned` | ₹1,88,259.09 | ₹426.98 | 3 | ₹0.00 | 0 |
| r0_base | `encore_learned_nopayday` | ₹1,88,259.09 | ₹435.97 | 3 | ₹0.00 | 0 |
| r1_shifted | `immediate_x3` | ₹0.00 | ₹0.00 | 0 | ₹2,07,341.00 | 0 |
| r1_shifted | `fixed_t123` | ₹52,774.63 | ₹31.01 | 3 | ₹1,68,235.00 | 0 |
| r1_shifted | `fixed_spread10` | ₹1,43,001.35 | ₹96.33 | 3 | ₹1,01,377.00 | 0 |
| r1_shifted | `random_in_horizon` | ₹2,20,425.10 | ₹166.16 | 3 | ₹44,006.00 | 0 |
| r1_shifted | `encore_learned` | ₹1,50,291.50 | ₹104.67 | 3 | ₹95,975.00 | 0 |
| r1_shifted | `encore_learned_nopayday` | ₹1,54,867.75 | ₹111.20 | 3 | ₹92,584.00 | 0 |
| r2_no_signal | `immediate_x3` | ₹0.00 | ₹0.00 | 0 | ₹2,63,444.00 | 0 |
| r2_no_signal | `fixed_t123` | ₹34,005.26 | ₹16.09 | 3 | ₹2,37,600.00 | 0 |
| r2_no_signal | `fixed_spread10` | ₹81,938.16 | ₹41.05 | 3 | ₹2,01,171.00 | 0 |
| r2_no_signal | `random_in_horizon` | ₹1,18,831.58 | ₹62.24 | 3 | ₹1,73,132.00 | 0 |
| r2_no_signal | `encore_learned` | ₹1,07,677.63 | ₹56.71 | 3 | ₹1,81,609.00 | 0 |
| r2_no_signal | `encore_learned_nopayday` | ₹1,07,411.84 | ₹57.09 | 3 | ₹1,81,811.00 | 0 |

**The six policies, and what each one is for:**

- `immediate_x3` — retries one hour after failure, three times. A floor.
- `fixed_t123` — T+1/T+2/T+3 at 23:00. **Razorpay's documented subscription
  auto-retry shape**, so this is the industry-standard comparison.
- `fixed_spread10` — T+3/T+6/T+9 at 23:00. Same 10-day reach as the learned
  policy, spent with no model at all. *Horizon-matched heuristic.*
- `random_in_horizon` — identical candidate set and identical cooldown-aware
  start to `LearnedPolicy`, hour drawn uniformly at random.
  ***Horizon-matched scientific control.***
- `encore_learned` — the trained model.
- `encore_learned_nopayday` — the same model with the hardcoded
  `day_of_month in (1, 2, 7, 8)` feature removed. See §7.

**What the table says, stated plainly:**

- **The headline claim that survives is `encore_learned` beating
  `fixed_t123` by 2.85x on the held-out `r1_shifted` regime.** That is a
  real product result: `fixed_t123` is what the industry actually does.
- **The claim that does NOT survive is that the model learned useful
  timing.** On `r1_shifted` the uniform-random control recovers
  ₹2,20,425.10 against the model's ₹1,50,291.50 — **random wins by 47%,
  using fewer attempts** (~1,327 vs ~1,436 per 1000 failures). Reproduced
  across four independent rng streams. The model only wins on `r0_base`,
  the regime it trained on, and only by 1–3%. Full analysis in §7 and
  `BROKELOG.md` entries 9 and 10.
- **`immediate_x3` recovers ₹0.00 in every regime by design, not by bug.**
  It retries an hour after failure, which always lands just outside the
  wall's 22:00–07:00 execution window, so it burns its entire 3-attempt
  budget on `outside_execution_window` and `cooldown_active` denials and
  never once reaches the rail. The wall enforcing the window *is* the
  lesson, and `runs/scoreboard.html`'s denial breakdown shows exactly which
  rule caught it.
- `compliance_violations` is `0` in all 18 cells — see the violations caveat
  in §7 for what that number can and cannot prove.
- Regimes: `r0_base` is what the models train on; `r1_shifted` moves the
  salary-day distribution later in the month and raises decline rates (a
  held-out distribution shift); `r2_no_signal` keeps `r0_base`'s rates but
  destroys the salary-day timing signal entirely (`uniform_credits=True`).
  See `src/encore/evaluate.py`'s `REGIMES` for the exact parameters.

## 3. Architecture

```mermaid
flowchart LR
    SIM["Simulator<br/>latent balance, declines, replies"] --> POL
    POL["Policy<br/>immediate_x3 / fixed_t123 / encore_learned"] --> WALL
    WALL["Wall<br/>pure compliance gate:<br/>hard-decline terminal, retry cap,<br/>cooldown, execution window, kill switch"] --> RAIL
    RAIL["Rail<br/>Simulated or Razorpay test-mode"] --> AUDIT
    AUDIT["Audit log<br/>append-only JSONL + idempotency ledger"] --> METRICS
    METRICS["Metrics / Scoreboard<br/>eval.json, scoreboard.html"]

    REPLIES["Customer replies"] --> PARSER
    PARSER["Parser<br/>keyword fallback or LLM<br/>through pydantic ReplyIntent"] --> KILL
    KILL["Kill set<br/>cancel intents only"] --> WALL
```

The LLM parser (`src/encore/parser.py`'s `parse_llm`) only ever sees customer
replies, and only ever produces a `pydantic`-validated `ReplyIntent`. It
cannot propose an amount, an hour, or a retry — it can only add a
`customer_id` to the kill set the wall checks first, before anything else.
It never touches the rail.

## 4. Quickstart

```bash
uv sync
uv run pytest
uv run encore eval
uv run encore report
```

`uv run encore eval` runs the full regime × policy matrix and writes
`runs/eval.json`; `uv run encore report` reads that file and writes
`runs/scoreboard.html` (the source of the table in section 2). Bulk metrics
come from the simulator; the demo slice proves the rail integration is
real. To see the real Razorpay test-mode rail exercised end to end without
touching the network or spending a real `reference_id`, run:

```bash
uv run encore demo --dry-run
```

`encore demo` routes each planned action through the same `wall.decide()`
check and kill set `encore eval`'s scheduler uses — a killed customer or a
wall-denied action never reaches link creation, only prints why and moves
on. `--dry-run` runs that identical path against `SimulatedRail` instead of
the live Razorpay client, so it exercises the full wall/kill-set/audit
logic with no network call and no real link.

## 5. Where we chose not to use AI

- **The wall never sees a model.** `src/encore/wall.py` is a pure function
  of `(action, state, config)` — no I/O, no clock, no randomness, no LLM
  call, enforced by project rule (`CLAUDE.md`: "wall.py stays pure").
  Whether a retry is legal is a deterministic compliance check, not
  something worth a model's judgment.
- **The stopping rule is one comparison, not a model.** `LearnedPolicy`'s
  decision to give up on a customer (`src/encore/model.py`) is
  `probs[best] * amount < cost_per_attempt`: a plain expected-value
  threshold. The model only ever picks *which hour*, inside a horizon the
  wall has already filtered to legal candidates; whether to *keep trying at
  all* is arithmetic.
- **Money math is integer paise for every stored or transacted amount.** No
  float ever touches a stored or transacted amount anywhere in the codebase
  — not in the simulator, not in the scheduler, not in the ledger, not in
  the rail call. Floats appear in exactly three places, all derived
  reporting or display, never a value that gets stored, compared by the
  wall, or sent to the rail: `evaluate.py::run_matrix`'s
  `recovered_per_1000_failures_paise` and `recovery_per_attempt_paise`
  (float division, rounded back to an integer paise count before it's
  written to `eval.json`), and `demo.py`'s operator-facing print of
  `amount_paise / 100:.2f` (display only, immediately discarded, never
  stored or compared). The scoreboard's rupee formatter
  (`src/encore/report.py::format_rupees`) stays float-free — integer
  `divmod`, no float at all — converting a paise integer to a `₹` string at
  the very last step. An LLM producing a number that becomes money is
  exactly the failure mode this project refuses to build.
- **The reply parser defaults to keywords, not an LLM, on the money-adjacent
  path.** `parse_keyword` (regex over Hindi/Hinglish cancel and promise
  words) is the default `parse_fn` used by `encore eval`'s kill-set
  construction. Its real, measured accuracy against the 40-row labeled set
  in `data/reply_eval.jsonl` (pinned by
  `tests/test_parser.py::test_evaluate_keyword_parser_on_labeled_set`) is:

  | Parser | accuracy (kind) | accuracy (kind + promise_day) | n |
  |---|---:|---:|---:|
  | keyword | 27/40 = **0.675** | 27/40 = **0.675** | 40 |
  | claude-haiku-4-5 | not yet measured — needs `ANTHROPIC_API_KEY` | — | 40 |
  | claude-sonnet-5 | not yet measured — needs `ANTHROPIC_API_KEY` | — | 40 |

  All 6 of the labeled set's `dispute` cases are missed — `parse_keyword`
  has no dispute detector at all and can never emit `kind="dispute"`, so
  every dispute reply falls through to `other`. That's the real gap the LLM
  columns exist to test. Run `uv run encore parse-eval` yourself (it
  auto-loads `ANTHROPIC_API_KEY` from `.env` via `load_dotenv()`) to
  populate the `claude-haiku-4-5` / `claude-sonnet-5` rows — without a key
  set, the command prints the keyword row above and explicitly says it is
  skipping the LLM rows, rather than inventing numbers for them. This
  README does not claim LLM-parser numbers that have not actually been run.
  Whichever parser wins on `dispute` recall, it still only ever feeds the
  kill set — it never proposes a retry, an hour, or an amount.

## 6. Prior art

| Product | Approach | Delta from Encore |
|---|---|---|
| [Stripe Smart Retries](https://stripe.com/en-gr/docs/billing/revenue-recovery/smart-retries) | ML timing model over 500+ attributes, no published compliance boundary specific to Indian mandates | Encore's model never gets a vote on legality — a NPCI-shaped wall does, and it's tested to catch a forged violation |
| [Chargebee Revive](https://www.chargebee.com/payments/retries-and-dunning/) | 200+ signals per failure, billing-context-aware retry timing | Same category of "when," no public claim of a hard, independently-checked compliance gate |
| [GoCardless Success+](https://gocardless.com/solutions/success-plus) | ML-picked retry date, NSF-failures only, 3 retries / 4-week window | Closest in shape (compliant-window retry timing); Encore's contribution is the wall/policy split and a post-hoc violation checker, not a better model |
| Razorpay's own fixed T+1/T+2/T+3 [subscription retries](https://razorpay.com/docs/payments/subscriptions/payment-retries/) | Fixed schedule, no learning | This is Encore's `fixed_t123` baseline, not a competitor — the metrics table above is the direct comparison |
| [Razorpay Intelligent Payment Retry](https://razorpay.com/blog/razorpay-intelligent-payment-retry/) | Checkout-time payment-*method* suggestion when a live card payment fails | Different problem entirely (real-time UX at checkout, not a scheduled recurring-mandate retry) — out of scope for Encore, mentioned only to avoid confusion with the name |

## 7. Honest limitations

- **The oracle and the rail deliberately diverge on `churn_intent`.**
  `Portfolio.would_succeed` (the labeling oracle used to train the model)
  returns `False` for any customer with latent `churn_intent=True`, even if
  their balance is sufficient — modeling "would pay if nudged, but won't
  stay a customer" as unrecoverable for training purposes. `Portfolio.debit`
  (the mechanical rail every policy is actually scored against) has no such
  check — it debits successfully if the balance clears, `churn_intent` or
  not. This affects ~5% of customers (`churn_intent=True` at `rng.random() <
  0.05`, `src/encore/simulator.py`). The bias runs **against** the learned
  policy, never for it: the model is trained to be pessimistic about
  customers the rail will actually let it recover, not the other way
  around. Pinned by
  `tests/test_simulator.py::test_churn_intent_diverges_oracle_from_debit`.
- **`compliance_violations: 0` is real, but only for what can be re-checked
  after the fact.** `evaluate.py::count_violations` replays every execution
  record's audit trail through the wall independently, and does correctly
  re-verify hard-decline-terminal, the 3-retry cap, and the execution
  window. It **cannot** re-verify `cooldown_active` post-hoc: the audit log
  has no field recording a sequence's *previous* attempt hour, so
  `last_attempt_hour` can't be reconstructed from execution records alone,
  and the checker passes `None` for it — which disables only that one wall
  check (`decide()` skips the cooldown branch on `None`). Cooldown is
  enforced live, at run time, by the same `wall.decide()` every attempt
  actually goes through — it is not unverified, just not *independently
  re-verifiable* after the fact from the audit log as it currently exists.
  See the docstring on `count_violations` in `src/encore/evaluate.py`.
- **The horizon-matched control beats the learned policy. The ML is not the
  reason this works.** An earlier version of this section called the win
  "likely a horizon artifact" and said the experiment "has not been run."
  It has now been run, and it confirmed the suspicion — with a larger margin
  than expected. `random_in_horizon` draws its retry hour **uniformly at
  random** from the identical candidate set `LearnedPolicy` ranks, starting
  from the identical cooldown-aware hour (`policies.legal_candidate_hours`
  and `policies.cooldown_aware_start` are shared by both — pinned by a test
  asserting object *identity*, not equality, so the control cannot drift).
  Results, recovered per 1000 failures:

  | Regime | `random_in_horizon` | `encore_learned` | Winner |
  |---|---:|---:|---|
  | `r0_base` *(trained on)* | ₹1,82,359.09 | ₹1,88,259.09 | learned, by 3% |
  | `r1_shifted` *(held-out)* | **₹2,20,425.10** | ₹1,50,291.50 | **random, by 47%** |
  | `r2_no_signal` | **₹1,18,831.58** | ₹1,07,677.63 | **random, by 10%** |

  Not a brute-force win: on `r1_shifted` the control recovered more money
  with **fewer** attempts (~1,327 vs ~1,436 per 1000 failures), and the wall
  caps every policy at 3 retries identically. Reproduced across four
  independent rng streams (ratios 1.47, 1.48, 1.47, 1.51 on `r1_shifted`;
  4/4). Note also that `fixed_spread10` — a dumb T+3/T+6/T+9 heuristic with
  no model whatsoever — reaches 2.71x on `r1_shifted`, i.e. most of the
  headline multiple is available with no learning at all. **The surviving
  claim is "beats the industry-standard T+1/T+2/T+3 schedule 2.85x," not
  "learned when customers have money."** `BROKELOG.md` entry 9.

- **Why it fails is a two-day miss at a step function, not a bad feature.**
  The first hypothesis — that the hardcoded `day_of_month in (1, 2, 7, 8)`
  "near-payday flag" in `model.featurize` was the culprit — was tested and
  **was wrong**. `encore_learned_nopayday` (same model, flag removed,
  `day_of_month` retained so timing stays learnable) moved `r1_shifted` from
  ₹1,50,291.50 to only ₹1,54,867.75, still 0.70x of random. Measuring where
  retries actually land found the real cause. In `r1_shifted` (salary days
  `[3, 10, 25]`, weights `[0.2, 0.3, 0.5]`) success is a **step function at
  day 25**:

  ```
  encore_learned    day   21  22  23  24  25  26  27
                    tried 165  24 219 138  14  56  46
                    win%    2%  0%  3%  0%100%100%100%
  ```

  The model concentrates 384 of ~1,064 retries on days 21 and 23 — two days
  before salary lands, where success is 2–3% — and places just 14 on day 25.
  Over days 25–30 it lands ~151 retries against the random control's ~237.
  Against a wall-enforced 3-retry budget, that gap is the entire difference.
  The model is not ignoring payday; it targets that window slightly *more*
  than random (23.9% vs 20.8% of retries in days 24–27). It is
  systematically ~2 days early, and earliness at a step function is
  indistinguishable from being wrong. A confident near-miss is worse than no
  opinion, because it spends a capped budget on days that are reliably empty.
  `BROKELOG.md` entry 10.

- **That step function is a simulator artifact, and the magnitude of the
  above is flattered by it.** `Portfolio.debit` succeeds deterministically
  once the balance clears, so post-payday success is exactly 100% and
  pre-payday is near 0%. Real balances do not behave like a light switch,
  and a 2-day error would almost certainly be punished less harshly in
  production. The *direction* of the finding is sound; treat the 47% as
  simulator-specific. Also unestablished: *why* the model settles on days
  21–23 specifically. An asymmetric-loss retrain (penalising early retries
  harder than late ones) is the obvious next experiment and has not been run.

- **Months are 30 days, always** (`DAYS_PER_MONTH = 30`,
  `src/encore/domain.py`). No real calendar, no leap years, no 28/29/31-day
  variation.
- **Every rupee figure is simulator-relative.** `recovered_per_1000_failures`
  and every other money figure in this README come from a synthetic
  `Portfolio`, not a production ledger. Read the table as *policy A beats
  policy B on this simulator's rules*, not as a real-world revenue lift
  claim.
- **What test mode cannot prove.** Razorpay's test account used for this
  build offers no UPI checkout method at all — only Cards, Netbanking, and
  Wallet (`docs/spike-notes.md`, `BROKELOG.md`'s first entry) — so nothing
  here exercises the actual UPI AutoPay execution path end to end; all
  "real rail" evidence is via Netbanking's mock bank page instead. More
  fundamentally, a failed payment attempt does **not** move a Payment
  Link's `status` out of `created` — `created` is indistinguishable from
  "nobody has tried yet" from the polling API alone
  (`docs/spike-notes.md`, "Key finding for Task 11's polling design"). The
  demo's poller therefore classifies real failures as
  `no_terminal_status_within_timeout`, never as an explicit `failure` — test
  mode can prove the success path and the timeout path, but not a clean
  positive "the bank declined this" signal from the API surface actually
  used here.
- **NPCI rules are modeled on, with citations — never claimed as
  compliant.** `WallConfig`'s retry cap, cooldown, and execution window
  (`src/encore/wall.py`) are shaped by the NPCI retry-allowance and
  non-peak-window reporting cited in section 1, and by no formal compliance
  review, legal sign-off, or NPCI certification. This project models the
  publicly reported shape of the rule; it does not claim to be an NPCI- or
  RBI-compliant system, and nothing here should be read as such.

## Other references

- `BROKELOG.md` — the append-only record of what broke while building this
  and how each was resolved, seven entries as of this commit. Not
  duplicated here; read it directly for the real failures, root causes, and
  fix commits behind several of the numbers and caveats above.
- `AGENTS.md` — repo map, exact commands, and the non-negotiable engineering
  rules, written for whoever (human or agent) picks this repo up next.
