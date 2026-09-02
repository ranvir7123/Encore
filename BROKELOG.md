# Broke-log

Append-only record of what broke while building Encore. Read
[CLAUDE.md](CLAUDE.md) for the entry rules. The "what broke and how you got
out" submission answer is assembled from this file — entries are never
edited after the fact.

### 2026-08-31 — Razorpay test-mode UPI simulation not available on Payment Links checkout

- **What happened:** The build plan (Task 2 brief) assumed the standard
  Razorpay test-mode UPI trick — pay a Payment Link with UPI id
  `success@razorpay` or `failure@razorpay` to deterministically get a
  `paid` or failed outcome. In practice, when the controller opened the two
  spike checkout pages (https://rzp.io/rzp/4Jnj8Fz for `plink_TWLLefGUFjwjGf`
  and https://rzp.io/rzp/UB30CgC for `plink_TWLLmoEcAAGI4v`) in a real
  browser, **no UPI payment method was offered at all** — only Cards,
  Netbanking, and Wallet appeared. The UPI VPA flow described in the plan is
  impossible on this account as written.
- **Evidence:** Manual browser walkthrough by the controller, both spike
  links. Checkout for both `plink_TWLLefGUFjwjGf` and `plink_TWLLmoEcAAGI4v`
  showed only Cards / Netbanking / Wallet tabs — see
  `docs/spike-notes.md` ("Findings vs. plan assumptions" and "Manual
  checkout (browser-driven)" sections) for the full writeup. Netbanking was
  used instead, routing to Razorpay's simulated bank page which exposes
  explicit "Success"/"Failure" buttons; this produced `pay_TWLTaB6r7Epvnz`
  (captured, spike-001) and `pay_TWLWl8NzNSEN6q` (failed, spike-002).
- **Root cause:** Test-mode UPI simulation is not enabled/offered for this
  vanilla test account's Payment Links checkout — Razorpay does not surface
  a UPI option there, so the documented `success@razorpay` /
  `failure@razorpay` VPA convenience path cannot be exercised on this setup.
- **Fix:** n/a — this is a platform/account limitation, not a bug in our
  code, so there is no code fix. Documented workaround: use Razorpay's
  test-mode Netbanking flow, which routes to a mock bank page with explicit
  Success/Failure buttons, as the substitute for the UPI VPA trick. This is
  now the documented mechanism for Task 10/11's test-mode payment
  simulation. Landed together with the rest of the Task 2 spike work in
  commit `a48b751` ("feat: razorpay client + test-mode spike notes").
- **Still open:** Whether UPI becomes available on this account later (e.g.
  after KYC/activation) is unknown and was not investigated further, since
  Netbanking already provides a deterministic success/failure repro path.
  Also open: whether Razorpay's UPI VPA test simulation requires a
  different account tier/region setting — not researched, out of scope for
  this spike.

### 2026-08-31 — Plan's own scheduler test fails: 60-day world bills customers twice under one cycle_id

- **What happened:** Task 7 brief's `tests/test_scheduler.py`, transcribed
  verbatim, fails `test_no_hard_decline_is_ever_executed` deterministically
  (seed=42, reproduced on repeated runs) even though `src/encore/scheduler.py`
  and `src/encore/policies.py` were also transcribed verbatim from the brief
  and no transcription error was found (`diff --strip-trailing-cr` against
  the brief's code blocks showed byte-identical content). Real failing
  output:

  ```
  tmp_path = WindowsPath('C:/Users/RANVIR/AppData/Local/Temp/pytest-of-RANVIR/pytest-63/test_no_hard_decline_is_ever_e0')

      def test_no_hard_decline_is_ever_executed(tmp_path):
          p, failures = build_world()
          run(FixedSchedule(), tmp_path, p, failures)
          log = AuditLog(tmp_path / "audit.jsonl").read_all()
          hard_customers = {f.customer_id for f in failures
                           if f.decline in {DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED,
                                            DeclineCode.RISK_DECLINED}}
          executed = {r["customer_id"] for r in log if r["event"] == "execution"}
  >       assert not (hard_customers & executed)
  E       AssertionError: assert not ({'cust_0006', 'cust_0010', 'cust_0014', 'cust_0017', 'cust_0018', 'cust_0034', ...} & {'cust_0001', 'cust_0009', 'cust_0027', 'cust_0035', 'cust_0042', 'cust_0048', ...})

  tests\test_scheduler.py:43: AssertionError
  =========================== short test summary info ===========================
  FAILED tests/test_scheduler.py::test_no_hard_decline_is_ever_executed - Asser...
  1 failed, 3 passed in 0.33s
  ```

  `cust_0042` evidence, pulled from a standalone repro script dumping
  `failures` and the audit log for that customer:

  ```
  failures for cust_0042: [
      (INSUFFICIENT_FUNDS, at_hour=174, cycle_id='c1'),   # month 1: soft decline
      (MANDATE_REVOKED,    at_hour=894, cycle_id='c1'),   # month 2: hard decline
  ]
  {'event': 'decision', 'customer_id': 'cust_0042', 'attempt_id': 'cust_0042:c1:retry:1', 'at_hour': 215, 'allowed': True, 'reason': 'ok', 'policy': 'fixed_t123'}
  {'event': 'execution', 'customer_id': 'cust_0042', 'attempt_id': 'cust_0042:c1:retry:1', 'at_hour': 215, 'outcome': 'failure', 'amount_paise': 19900, 'policy': 'fixed_t123'}
  {'event': 'decision', 'customer_id': 'cust_0042', 'attempt_id': 'cust_0042:c1:retry:2', 'at_hour': 239, 'allowed': True, 'reason': 'ok', 'policy': 'fixed_t123'}
  {'event': 'execution', 'customer_id': 'cust_0042', 'attempt_id': 'cust_0042:c1:retry:2', 'at_hour': 239, 'outcome': 'failure', 'amount_paise': 19900, 'policy': 'fixed_t123'}
  {'event': 'decision', 'customer_id': 'cust_0042', 'attempt_id': 'cust_0042:c1:retry:3', 'at_hour': 263, 'allowed': True, 'reason': 'ok', 'policy': 'fixed_t123'}
  {'event': 'execution', 'customer_id': 'cust_0042', 'attempt_id': 'cust_0042:c1:retry:3', 'at_hour': 263, 'outcome': 'failure', 'amount_paise': 19900, 'policy': 'fixed_t123'}
  {'event': 'park', 'customer_id': 'cust_0042', 'cycle_id': 'c1', 'policy': 'fixed_t123'}
  {'event': 'decision', 'customer_id': 'cust_0042', 'attempt_id': 'cust_0042:c1:retry:1', 'at_hour': 935, 'allowed': False, 'reason': 'hard_decline_terminal', 'policy': 'fixed_t123'}
  ```

  The three executions (all `outcome: failure`) belong to the *soft-decline*
  sequence (hour 174) and never succeed — the sequence just parks. The
  *hard-decline* sequence (hour 894) is correctly denied `hard_decline_terminal`
  on its only attempt and never reaches `rail.execute`. The wall/scheduler
  enforce "never execute a hard-decline retry" correctly, per sequence.

- **Root cause:** `src/encore/domain.py` sets `DAYS_PER_MONTH = 30`, and
  `Portfolio.run_cycle` bills a customer whenever `day_of_month(h) ==
  c.billing_day`, which wraps every 30 simulated days. The Task 7 test calls
  `p.run_cycle(60, "c1")` — a 60-day world — so a customer whose billing_day
  falls in that window bills **twice**, both occurrences tagged with the
  same caller-supplied `cycle_id="c1"` (it's a constant, not generated per
  occurrence). `test_no_hard_decline_is_ever_executed` then groups by bare
  `customer_id` (`hard_customers` / `executed` sets), conflating the two
  independent billing sequences. When one occurrence is a soft decline that
  gets retried (even unsuccessfully) and the other is an unrelated hard
  decline, the intersection is non-empty even though no hard-decline retry
  was ever executed. Confirmed this is the general mechanism: `Counter` over
  `failures` by `customer_id` for seed=42 shows 25 of 300 customers appear
  twice (97 total failures), and several mix a soft decline in one
  occurrence with a hard decline in the other — that's what produces the
  intersection.
- **Fix:** `8f787ae`. Changed
  `tests/test_scheduler.py`'s `build_world` to
  call `p.run_cycle(30, "c1")` instead of `run_cycle(60, "c1")` so each
  customer bills at most once per run and the test's per-customer grouping
  assumption holds. No production code (`scheduler.py`, `policies.py`) was
  touched — the controller ruled this a plan/test defect, not an
  implementation bug, and the fix scope was limited to the test's `days`
  argument plus an explanatory comment. All 4 scheduler tests pass at 30
  days; full suite and `ruff check` both pass — see
  `.superpowers/sdd/encore-build-plan/task-7-report.md` for the real
  command output.
- **Still open:** Two failures for the same customer within one
  `run_cycle` call share the same `cycle_id` (it's a parameter, not derived
  per billing occurrence), so their `attempt_id`s
  (`customer_id:cycle_id:kind:attempt_no`) collide across sequences — e.g.
  sequence 2's retry attempt 1 has the identical `attempt_id` as sequence
  1's retry attempt 1. `AttemptLedger.already_executed` would treat the
  second sequence's first attempt as a duplicate of the first sequence's,
  even though they're unrelated debits. This doesn't bite in Task 7 because
  hard declines are denied by the wall before ever reaching the ledger, and
  the 30-day fix avoids the double-billing case entirely for this test. But
  Task 10's evaluation harness needs to either keep `run_cycle` windows to
  one billing period per `cycle_id`, or generate a distinct `cycle_id` per
  billing occurrence (e.g. include the billing month/day in the id) — not
  investigated further here, flagged for whoever builds Task 10.

### 2026-08-31 — Plan's training-data volume estimate wrong: 200x2-seed world yields 384 rows, test demanded >500

- **What happened:** Task 8 brief's `tests/test_model.py::test_training_data_has_both_labels`,
  transcribed verbatim, calls
  `generate_training_data(R0, n_customers=200, seeds=[1, 2])` and asserts
  `len(X) == len(y) > 500`. `src/encore/model.py`'s `generate_training_data`,
  also transcribed verbatim from the brief, produced exactly 384 rows for
  that call — deterministically, confirmed on repeated runs. Real failing
  output:
  ```
  def test_training_data_has_both_labels():
      X, y = generate_training_data(R0, n_customers=200, seeds=[1, 2])
      assert len(X) == len(y) > 500
  E       assert 384 > 500
  E        +  where 384 = len([1, 1, 1, 1, 1, 1, ...])
  tests\test_model.py:17: AssertionError
  ```
- **Evidence:**
  ```
  $ uv run pytest tests/test_model.py -q
  .F..
  ================================== FAILURES ===================================
  _____________________ test_training_data_has_both_labels ______________________
      def test_training_data_has_both_labels():
          X, y = generate_training_data(R0, n_customers=200, seeds=[1, 2])
  >       assert len(X) == len(y) > 500
  E       assert 384 > 500
  E        +  where 384 = len([1, 1, 1, 1, 1, 1, ...])
  tests\test_model.py:17: AssertionError
  =========================== short test summary info ===========================
  FAILED tests/test_model.py::test_training_data_has_both_labels - assert 384 >...
  1 failed, 3 passed in 116.17s
  ```
  A standalone diagnostic script calling the exact same
  `generate_training_data(R0, n_customers=200, seeds=[1, 2])` printed
  `len(X) = 384`, `sum(y)/len(y) = 0.8463541666666666` (label balance is
  fine — this is a pure row-count shortfall, not a degenerate-label
  problem). The sibling test's larger world,
  `generate_training_data(R0, n_customers=300, seeds=[1, 2, 3])`, produced
  `len(X2) = 636` rows and a holdout accuracy of `0.90625` on the
  `test_model_beats_coin_flip_on_holdout_split` 80/20 split — comfortably
  above both bars.
- **Root cause:** The brief's row-count expectation (`> 500` from a
  200-customer, 2-seed world) didn't survive contact with the simulator's
  actual soft-decline rate. `Portfolio.generate` seeds each customer's
  starting balance at `rng.randint(0, 3 * amount)` and credits a full
  salary (`rng.randint(15_00000, 60_00000)`) on `salary_day`, so most
  customers stay solvent by the time their `billing_day` debit fires; only
  ~4% of billing attempts actually soft-decline (insufficient funds, issuer
  down, or gateway timeout) in a 200x2-seed world over `run_cycle(60, ...)`.
  Each soft-decline failure contributes exactly 12 rows
  (`rng.sample(_legal_candidates(...), 12)`), so 32 soft-decline failures x
  12 = 384 rows — short of the `> 500` bar the brief assumed. The
  `n_customers=300, seeds=[1, 2, 3]` world used by the sibling holdout test
  produces proportionally more failures (53 x 12 = 636) and clears the bar
  with margin.
- **Fix:** `4098fd7`. Changed `tests/test_model.py::test_training_data_has_both_labels`
  to call `generate_training_data(R0, n_customers=300, seeds=[1, 2, 3])` — the
  exact world size the sibling `test_model_beats_coin_flip_on_holdout_split`
  test already proved yields 636 rows (>500 with margin, deterministic),
  with a one-line comment pointing back to this entry. The `> 500` and
  label-balance assertions were left unchanged; no threshold, seed, or
  simulator code was touched. All 4 tests in `tests/test_model.py` pass;
  full suite (42 tests) and `ruff check .` both pass — see
  `.superpowers/sdd/encore-build-plan/task-8-report.md` for the real command
  output.
- **Still open:** nothing.

### 2026-08-31 — Task 10 eval matrix: encore_learned ties, not beats, fixed_t123 on recovered money in every regime

- **What happened:** Task 10 brief's Step 5 states "the learned policy should
  beat both baselines on r1 and collapse toward them on r2." The real matrix
  (`uv run python -m encore.evaluate`, seeds `[100, 101, 102]`,
  `n_customers=500`) instead shows `recovered_per_1000_failures_paise` for
  `encore_learned` and `fixed_t123` **bit-for-bit identical** in all three
  regimes (r0_base, r1_shifted, r2_no_signal) — not close, not "collapsed
  toward," but exactly equal to the paisa.
- **Evidence:** `runs/eval.json` (also pasted verbatim in
  `.superpowers/sdd/encore-build-plan/task-10-report.md`):
  `r0_base`: both 18825909; `r1_shifted`: both 27981242; `r2_no_signal`: both
  13668289. A standalone diagnostic script re-read the per-seed audit
  JSONL files still on disk under `runs/` and compared, for every
  (regime, seed) pair, the exact set of customers each policy successfully
  debited and the exact total paise recovered:
  ```
  r0_base      100 n_fixed 22  n_learned 22  same_customer_set True same_total_amount True
  r0_base      101 n_fixed 30  n_learned 30  same_customer_set True same_total_amount True
  r0_base      102 n_fixed 31  n_learned 31  same_customer_set True same_total_amount True
  r1_shifted   100 n_fixed 156 n_learned 156 same_customer_set True same_total_amount True
  r1_shifted   101 n_fixed 157 n_learned 157 same_customer_set True same_total_amount True
  r1_shifted   102 n_fixed 146 n_learned 146 same_customer_set True same_total_amount True
  r2_no_signal 100 n_fixed 63  n_learned 63  same_customer_set True same_total_amount True
  r2_no_signal 101 n_fixed 67  n_learned 67  same_customer_set True same_total_amount True
  r2_no_signal 102 n_fixed 91  n_learned 91  same_customer_set True same_total_amount True
  ```
  All 9 (regime, seed) cells: identical customer set, identical total paise,
  every single time — while the actual attempt hours chosen were almost
  always different (156/156 matched successes in `r1_shifted` seed 100 used
  a different `at_hour`; only 5/156 even landed in the same day-bucket).
  `recovery_per_attempt_paise` (the per-attempt efficiency metric) does
  differ and does favor `encore_learned` in every regime: r0_base 48726 vs
  fixed's 47065; r1_shifted 44686 vs 43468; r2_no_signal 8459 vs 8445.
- **Root cause:** Two simulator properties combine to make the recovered-
  money *total* insensitive to which compliant day a policy retries on, as
  long as it uses its full retry budget: (1) `amount_paise` is fixed per
  customer (`src/encore/simulator.py`'s `Customer.amount_paise`, set once at
  `Portfolio.generate` and never varied by attempt), so it doesn't matter
  *which* successful day recovers a customer — the recovered amount is the
  same either way; (2) once a customer's balance clears the debit amount
  (typically right after their salary credit, which is 15-60x the daily
  spend), it stays cleared for a long stretch, because daily spend
  (`rng.randint(1000, 15000)`) is tiny relative to the salary credit
  (`rng.randint(15_00000, 60_00000)`) — so solvency is a near-monotonic,
  long-lived condition, not a narrow window a policy could miss by picking
  the wrong day. `FixedSchedule` (fixed T+1/T+2/T+3) and `LearnedPolicy`
  (model-guided, explores up to a 10-day horizon, same 3-attempt cap) end up
  "catching" the exact same population of eventually-solvent customers
  within their shared budget, just via different specific days/hours. Since
  `LearnedPolicy`'s stopping rule (`probs[best] * amount < cost: park`) is
  explicitly optimizing for cost-per-recovery, not for expanding which
  customers are ever reachable — and both policies share the same
  reachable ceiling (3 attempts each) — the *total* recovered money ties,
  while the *attempts needed* to reach that total is where `encore_learned`
  actually wins.
- **Fix:** n/a — this is not a bug in `evaluate.py`, `scheduler.py`, or the
  wall; it is a genuine structural property of how the simulator and the
  two compliant policies interact. Per Task 10's explicit instruction ("do
  NOT tune the simulator or model to force a win"), no simulator or model
  code was changed to manufacture the recovered-money win the brief
  predicted. The real, measurable win for `encore_learned` is
  `recovery_per_attempt_paise` — it recovers the identical total money
  using measurably fewer contact attempts in every regime, which is exactly
  what its cost-based stopping rule is designed to optimize.
  `compliance_violations` is 0 in all 9 cells either way.
  `immediate_x3` (the deliberately-dumb baseline) recovers **zero** paise in
  every regime: its "retry 1 hour after failure" schedule always lands
  outside the wall's 22:00-07:00 execution window on the first try
  (failures always occur at hour-of-day 6, so T+1 is hour-of-day 7 — just
  past the window boundary), and its own back-to-back proposals then trip
  `cooldown_active` on the remaining two tries before it exhausts its
  3-attempt budget and parks, having executed nothing. This matches the
  existing `test_immediate_retry_burns_attempts_on_window_denials`
  (`tests/test_scheduler.py`) and is the intended lesson of that baseline,
  not a new finding.
- **Still open:** whether a richer eval design (larger retry cap, a harder
  cost floor, or per-customer amounts that vary by attempt) would make the
  recovered-money *ceiling* itself distinguishable between compliant
  policies was not investigated — out of scope for Task 10, whose
  instruction was to report the real numbers the harness produces, not
  redesign the eval to produce a different headline shape.

### 2026-08-31 — Oracle labels were time-invariant: would_succeed read end-of-cycle balance for every candidate hour

- **What happened:** Code review of the Task 8 ML core (already believed
  done — main commit `4098fd7` merged and pushed) found that
  `Portfolio.would_succeed(customer_id, at_hour)` in `src/encore/simulator.py`
  checked `c.balance_paise >= c.amount_paise`, where `c.balance_paise` is a
  single mutated scalar on the `Customer` object reflecting whatever the
  balance happened to be at the moment `would_succeed` is called (i.e.
  end-of-`run_cycle` state), regardless of the `at_hour` argument. Since
  `generate_training_data` calls `p.would_succeed(f.customer_id, h)` *after*
  `p.run_cycle(60, ...)` has already finished mutating every customer's
  balance to its final value, all 12 candidate-hour labels sampled for a
  given failure get the identical answer (except on the rare hour that
  lands inside `issuer_down_hours`, which is genuinely time-varying). The
  `at_hour` parameter — the only thing that's supposed to vary across the
  12 samples per failure — carried essentially no timing signal into the
  balance check, undermining the entire premise of "learn WHEN to retry":
  regime `R2` (`uniform_credits=True`, destroys the salary-day signal) and
  regime `R0`/`R1` should have produced measurably different learned
  timing behavior, but with time-invariant balance labels there was no
  timing signal for any regime to differ on.
- **Evidence:** Standalone repro script sampling the same 12 candidate
  hours `generate_training_data` uses for five real failures from
  `Portfolio.generate(200, R0, seed=1).run_cycle(60, "train_1")`:
  ```
  cust_0004 insufficient_funds labels: [True, True, True, True, True, True, True, True, True, True, True, True] unique: {True}
  cust_0051 insufficient_funds labels: [True, True, True, True, True, True, True, True, True, True, True, True] unique: {True}
  cust_0109 insufficient_funds labels: [True, True, True, True, True, True, True, True, True, True, True, True] unique: {True}
  cust_0146 insufficient_funds labels: [True, True, True, True, True, True, True, True, True, True, True, True] unique: {True}
  cust_0167 insufficient_funds labels: [True, True, True, True, True, True, True, True, True, True, True, True] unique: {True}
  ```
  All 12 candidate hours per failure — spread across a 10-day window with
  different days-of-month, hours-of-day, and days-since-failure — produced
  the exact same label. `Customer.balance_paise` is a plain mutated `int`
  field (`src/encore/simulator.py`'s `Customer` dataclass); nothing in
  `would_succeed` reconstructed what the balance actually was at `at_hour`
  specifically.
- **Root cause:** `would_succeed` was written to check the *current*
  (end-of-simulation) balance instead of the balance *as of `at_hour`*,
  because `Portfolio` never recorded balance history — only the live
  scalar `c.balance_paise`, updated in place once per simulated day inside
  `_advance_hour`. `debit()` correctly uses the live balance because it
  represents "attempt a real debit right now," but `would_succeed` is
  meant to answer a counterfactual ("if we retried at this specific future
  hour, would it succeed?") and had no per-hour balance data to answer
  that counterfactually — it silently degraded to "would it succeed at the
  end of the simulated window," true for all 12 sampled hours per failure
  bar the issuer-down check.
- **Fix:** `62467c0`. Added a `balance_history: dict[str, list[int]]` field
  to `Portfolio`, populated with one snapshot per customer per simulated
  day inside `_advance_hour` (no RNG consumed, no reordering of existing
  RNG draws). `would_succeed` now looks up the balance for
  `day = at_hour // HOURS_PER_DAY` from that history when the day was
  recorded, falling back to the current live `c.balance_paise` only when
  history is empty or the day is beyond what was recorded (keeps
  `test_oracle_agrees_with_debit_on_success`'s far-future query at hour
  `999_999` consistent with `debit()`, which always uses the live
  balance). `debit()`, `run_cycle`'s billing logic, and every RNG call
  sequence were left untouched. Same commit also fixed two related
  plan-mandated defects surfaced by the same review: `LearnedPolicy.propose`
  in `src/encore/model.py` now starts its candidate horizon past the
  wall's cooldown (`max(now_hour + 1, last_attempt_hour + cooldown_hours)`)
  instead of proposing hours the wall would deny for cooldown and burning
  retry budget on denials; and `propose` now scores candidates with the
  constant `attempt_no=1` instead of `state.retries_attempted + 1`, since
  training labels only ever exist for `attempt_no=1` (`generate_training_data`
  hardcodes it) — passing 2 or 3 at inference queried the model out of
  distribution on a feature it never saw vary. Determinism tests
  (`test_same_seed_same_world`, `test_different_seed_different_world`)
  still pass unchanged. Real before/after on
  `generate_training_data(R0, n_customers=300, seeds=[1, 2, 3])`: label
  balance moved from `0.830` (mostly-`True`, time-invariant) to `0.450`
  (now genuinely mixed, since timing actually matters); holdout accuracy
  on `test_model_beats_coin_flip_on_holdout_split` moved from `0.906` to
  `0.977`. Full suite (43 tests) and `ruff check .` both pass — see
  `.superpowers/sdd/encore-build-plan/task-8-report.md` for the real
  command output.
- **Still open:** nothing.

### 2026-08-31 — Time-blind rail made retry timing unmeasurable — rail now consults balance history

- **What happened:** The prior entry ("Task 10 eval matrix: encore_learned
  ties, not beats, fixed_t123...") diagnosed an exact, bit-for-bit tie
  between `encore_learned` and `fixed_t123` on total recovered money in
  every regime and every seed, and attributed it to a structural property
  of the simulator. The controller reviewed that diagnosis and ruled that
  the true cause was narrower and fixable: `SimulatedRail.execute` →
  `Portfolio.debit` always checked the *current* scalar
  `c.balance_paise`, which by the time any retry executes (all retries
  happen strictly after `run_cycle` has finished mutating every
  customer's balance to its final, end-of-window value) is the same
  end-of-cycle number regardless of which hour a retry actually lands
  on. So which day/hour a policy chose to retry on could change *how many
  attempts* it took, but never *whether* a customer was ultimately
  recoverable — collapsing any timing-based policy difference on the
  metric that matters (recovered money) down to zero. The plan's original
  "per-failure processing is not a correctness issue" simplification note
  (user-approved at the time) is deliberately reversed here on explicit
  controller instruction: the rail's execution outcome must now depend on
  the balance *as of the retry's actual hour*, exactly as `would_succeed`
  (the labeling oracle) already does, not on final-state balance.
- **Evidence:** `runs/eval.json` from the Task 10 real matrix run (pasted
  verbatim in `.superpowers/sdd/encore-build-plan/task-10-report.md`) shows
  `recovered_per_1000_failures_paise` identical between `fixed_t123` and
  `encore_learned` in all three regimes: r0_base both `18825909`; r1_shifted
  both `27981242`; r2_no_signal both `13668289`. A standalone diagnostic
  script re-reading the raw per-seed audit JSONL files confirmed this was
  not a rounding artifact — for all 9 (regime, seed) cells the two policies
  recovered the **identical set of customers** for the **identical total
  paise**, even though the specific attempt hours used were almost always
  different (in `r1_shifted` seed 100, all 156 matched successful
  customers used a different `at_hour` between the two policies, and only
  5/156 even landed in the same day-bucket).
- **Root cause:** `src/encore/simulator.py`'s `Portfolio.debit(customer_id,
  at_hour)` read `c.balance_paise` — a single mutated scalar reflecting
  whatever the balance happened to be at the moment `debit` is called
  (i.e., end-of-`run_cycle` state for every eval retry, since retries are
  scheduled and executed strictly after the failure-generating
  `run_cycle` call returns) — regardless of the `at_hour` argument. Every
  policy's retries, whichever hour they targeted, therefore all resolved
  against the exact same final balance snapshot. `Portfolio.would_succeed`
  had already solved this correctly (see the "Oracle labels were
  time-invariant" entry above, `62467c0`) by consulting
  `balance_history[day]` for `day = at_hour // HOURS_PER_DAY`; `debit`
  was never brought in line with it, so the mechanical rail and the
  labeling oracle diverged on exactly the axis ("does timing matter?")
  the eval harness exists to measure.
- **Fix:** User-directed reversal of the plan's "per-failure processing is
  not a correctness issue" simplification. `Portfolio.debit` now looks up
  the balance for `day = at_hour // HOURS_PER_DAY` from
  `balance_history[customer_id]` when history exists and the day is in
  range, falling back to the current live `c.balance_paise` only when
  history is empty or the day is beyond what was recorded — mirroring
  `would_succeed`'s pattern exactly, so `test_oracle_agrees_with_debit_on_success`'s
  far-future hour-`999_999` query and `test_churn_intent_diverges_oracle_from_debit`'s
  no-`run_cycle` (empty-history) case both still resolve through the same
  fallback both functions already agreed on. The `revoked` and
  `issuer_down_hours` checks, and the success-path deduction (which still
  comes off the live scalar, not the historical snapshot — eval worlds
  bill each customer at most once per run via `run_cycle(30, ...)`, so
  there is no double-collection path where that scalar/history divergence
  could matter), were left exactly as-is. `would_succeed`, `run_cycle`,
  and every RNG call sequence were left untouched. Fix commit: `869cdcf`.
- **Still open:** nothing.

### 2026-08-31 — Dry-run demo evidence went stale when the rail became time-aware
- **What happened:** Task 11's `--dry-run` evidence was captured (and quoted
  verbatim in `task-11-report.md`) *before* commit `869cdcf`
  ("fix: time-aware simulated rail...") landed on `main`. That transcript
  genuinely showed `status=paid outcome=success` for both sampled links at
  the time it was run. After `869cdcf`/`f911096` landed, the identical
  command (`uv run python -m encore.demo --dry-run --n 2`) deterministically
  produces `status=created outcome=no_terminal_status_within_timeout` for
  both links instead — not flaky, not a regression in `demo.py`'s own logic,
  but a genuine behavior change: `encore.demo`'s action always replayed each
  failure at `failed.at_hour`, the exact hour the debit already failed at,
  and the now-time-aware `SimulatedRail`/`Portfolio.debit` looks up simulated
  balance at that exact hour via `balance_history` — so a replay at the
  failure hour is now guaranteed to re-fail, every time, for every customer.
  The report presented the pre-fix transcript as current evidence when it no
  longer reflected the code's actual behavior, and the dry-run path could no
  longer exercise the success branch at all.
- **Evidence:** Pre-fix transcript, as originally captured and quoted in
  `task-11-report.md` (`uv run python -m encore.demo --dry-run --n 2`):
  ```
  cust_0113:demo_s100:retry:1: status=paid outcome=success
  cust_0403:demo_s100:retry:1: status=paid outcome=success
  ```
  Post-fix, same command, same seed, same code path (independently
  reproduced via a standalone script replaying the pre-fix `execute_at_hour
  = failed.at_hour` shape against the current `SimulatedRail`):
  ```
  total soft-decline failures available: 32
  at failed.at_hour (pre-fix replay hour): paid=0 created=32 of 32

  first 4 (matches --dry-run --n 4 ordering):
  cust_0113:demo_s100:retry:1: status=created outcome=no_terminal_status_within_timeout
  cust_0403:demo_s100:retry:1: status=created outcome=no_terminal_status_within_timeout
  cust_0092:demo_s100:retry:1: status=created outcome=no_terminal_status_within_timeout
  cust_0417:demo_s100:retry:1: status=created outcome=no_terminal_status_within_timeout
  ```
  0/32 of the seed-100/r0_base soft-decline failures succeed when replayed
  at their own original failure hour, confirmed exhaustively, not just on
  the first 2 or 4.
- **Root cause:** `encore.demo`'s `ProposedAction.execute_at_hour` was pinned
  to `failed.at_hour` — reasonable when `SimulatedRail.execute` consulted
  only the live end-of-cycle balance scalar (time-blind), but semantically
  wrong once `Portfolio.debit` became time-aware: replaying "would this
  debit succeed at the exact hour it already failed" against a time-aware
  balance history is definitionally the same failed query run twice, and
  will always return the same answer. The demo's own file (`demo.py`) was
  never touched by `869cdcf`/`f911096` — the semantic ground shifted under
  it from a change to a shared dependency (`simulator.py`), not from any
  edit to `demo.py` itself, which is why this wasn't caught until the next
  review pass specifically re-checked the demo's evidence against the
  current codebase.
- **Fix:** `execute_at_hour` changed from `failed.at_hour` to
  `failed.at_hour + 72` (a T+3-days retry, matching the product's own
  documented retry framing, e.g. `FixedSchedule`'s T+1/T+2/T+3 shape) in
  `src/encore/demo.py`. Re-verified post-fix: of the same 32 soft-decline
  failures, 13/32 now succeed and 19/32 time out at +72h — both the success
  and timeout branches are genuinely exercised by `--dry-run` again, not
  forced to one outcome. `attempt_id` does not include the hour, so
  reference_ids and ledger/idempotency behavior are unaffected. `demo.py`'s
  real-rail path is unaffected in substance -- the real API ignores
  `execute_at_hour` entirely (a human pays the link whenever they click
  through). Fix commit: `7c0b956`.
- **Still open:** nothing.

### 2026-09-01 — The demo script's own command now creates zero payment links

- **What happened:** `docs/demo-script.md`'s Beat 5 instructs the operator to
  record with `PYTHONUNBUFFERED=1 uv run python -m encore.demo --n 4
  --timeout 240`. Re-verified during handoff review: that command creates
  **no** payment links at all. Every one of the four attempts is
  short-circuited as an already-executed ledger hit, so there is nothing on
  screen to pay and the beat is unfilmable as written.
- **Evidence:** `runs/demo_ledger.txt` holds exactly four consumed
  `reference_id`s, and they are exactly the first four soft-decline failures
  `_first_n_soft_failures(4)` returns. Enumerated against the live ledger and
  the seed-100 kill set:
  ```
    n= 1  cust_0113  INR   999.00  LEDGER-HIT (skipped, no link)
    n= 2  cust_0403  INR   199.00  LEDGER-HIT + WALL-DENIED sequence_killed
    n= 3  cust_0092  INR   999.00  LEDGER-HIT (skipped, no link)
    n= 4  cust_0417  INR   199.00  LEDGER-HIT + WALL-DENIED sequence_killed
    n= 5  cust_0447  INR   199.00  FRESH -> creates a REAL payment link
  ```
  A second, independent instance of the same failure: running
  `--dry-run --n 24` and then `--dry-run --n 6` produced six skip lines and
  zero created links, because the dry-run keeps its *own* accumulating
  ledger (`runs/demo_ledger_dryrun.txt`, via `run_demo_slice`'s `_dryrun`
  suffix) that no document mentioned.
- **Root cause:** the four `reference_id`s in `demo_ledger.txt` were consumed
  by the original live evidence run recorded in commit `029db48` — the very
  run the script was written to reproduce. `AttemptLedger.already_executed`
  is checked *before* link creation, and is permanent by design, because a
  `reference_id` is consumed for good at Razorpay on first use. So the
  idempotency guarantee did precisely its job and, in doing so, made its own
  demonstration non-repeatable. Nothing in the code is wrong; the
  documentation encoded a command whose preconditions the code had already
  and irreversibly destroyed. The `--n` value was never re-derived after the
  evidence run, and neither ledger was treated as demo state.
- **Fix:** `docs/demo-script.md` Beat 5 rewritten and split — a free,
  networkless `--dry-run --n 8` beat (5a) that shows the wall denying two
  killed customers, preceded by a mandatory `rm -f
  runs/demo_ledger_dryrun.txt`; and a live `--n 5 --timeout 120` beat (5b)
  that creates exactly one fresh link (`cust_0447`, ₹199.00). The four
  ledger-hit lines are now narrated as the idempotency guarantee firing on
  camera rather than treated as noise. Also documented that polling is
  sequential per link at the full `--timeout`, so creating 7 links to pay 1
  costs ~24 minutes of dead terminal — the reason `--n 5` and not a larger
  value. Recorded here before fixing, per project rule. Fix commit: see the
  commit that follows this entry.
- **Still open:** `runs/demo_ledger.txt` must never be deleted — its
  `reference_id`s are permanently consumed at Razorpay and a delete would
  make the code re-attempt them and be rejected mid-recording. There is no
  guard in the code enforcing this; it is documented convention only. Each
  future re-record must raise `--n` past the high-water mark by hand.

### 2026-09-01 — The horizon-matched control beats the learned policy; the 2.85x was search width, not learned timing

- **What happened:** `README.md` section 7 already suspected that
  `encore_learned`'s win was "likely a horizon artifact" because
  `LearnedPolicy` searches a 10-day candidate window while `FixedSchedule`
  only tries T+1/T+2/T+3. The horizon-matched baselines were built to settle
  it. They settled it against us. A control that draws its retry hour
  **uniformly at random** from the identical 10-day candidate set beats the
  trained model on 2 of 3 regimes — including `r1_shifted`, the held-out
  distribution-shift regime the headline number is quoted from.
- **Evidence:** full matrix, seeds `100,101,102`, 500 customers each,
  recovered per 1000 failures:
  ```
  === r1_shifted ===
  fixed_t123           Rs 52,774.63   (1.00x)
  fixed_spread10       Rs143,001.35   (2.71x)
  random_in_horizon    Rs220,425.10   (4.18x)   <-- control
  encore_learned       Rs150,291.50   (2.85x)   <-- the headline claim
  ```
  Not a brute-force win: in `r1_shifted` the control recovered MORE money
  using FEWER attempts (~1,327 vs ~1,436 attempts per 1000 failures), and
  `max_contacts_per_customer` is 3 for both — the wall caps everyone
  identically. Repeated across four independent rng streams
  (`20260901, 11111, 22222, 33333`) via a monkeypatch of
  `evaluate.RANDOM_BASELINE_SEED`, with no production code altered:
  ```
  regime          random/learned ratio, by rng seed
  r0_base         0.97  0.99  0.98  0.99   -> learned wins, by 1-3%, 4/4
  r1_shifted      1.47  1.48  1.47  1.51   -> RANDOM wins, by 47-51%, 4/4
  r2_no_signal    1.10  1.12  1.10  1.07   -> RANDOM wins, by 7-12%, 4/4
  ```
- **Root cause:** two separate mistakes, one methodological and one in the
  feature set.
  (1) *Methodological:* the only baselines ever run were `immediate_x3` and
  `fixed_t123`, both of which can see at most 3 days past the failure.
  Search **width** and ranking **quality** were therefore never separated,
  and every reported multiple silently bundled them. `fixed_spread10` alone
  (a dumb T+3/T+6/T+9 heuristic with no model at all) recovers 2.71x in
  `r1_shifted` — i.e. most of the claimed 2.85x is reachable with no
  learning whatsoever.
  (2) *Feature set:* `model.featurize` includes
  `float(day_of_month(candidate_hour) in (1, 2, 7, 8))`, commented
  "near-payday flag". That is a hardcoded human prior, not a learned one,
  and it is tuned to `r0_base`, whose `salary_days=[1, 7, 15]` carry weights
  `[0.6, 0.3, 0.1]` — so 90% of customers are paid on day 1 or day 7 and the
  flag is a free correct answer. `r1_shifted` sets
  `salary_days=[3, 10, 25]` with weights `[0.2, 0.3, 0.5]`, putting **50% of
  customers on day 25**. The model's strongest feature then points
  confidently at the wrong end of the month, while a uniform draw over 10
  days catches day 25 by accident. This is why the model is not merely
  unhelpful under shift but actively *worse than chance*: it has a
  confident, wrong prior, and chance does not.
  The `r0_base` result is real but small and is the one place the prior is
  correct — learned wins by 1-3% there, using ~20% fewer attempts
  (441 vs 550 per 1000 failures), which is a genuine efficiency gain on the
  training distribution and nothing more.
- **Fix:** no fix to the model or the claim yet — this entry records the
  finding before any of that, per project rule. What *is* committed is the
  experiment that produced it: `policies.FixedSpread10` and
  `policies.RandomInHorizon`, `legal_candidate_hours` and
  `cooldown_aware_start` moved from `model.py` into `policies.py` so the
  control provably searches the same candidate set from the same starting
  hour (pinned by `tests/test_policies.py::
  test_learned_and_control_share_one_candidate_function`, which asserts
  identity, not equality), and both controls added to the eval matrix.
  13 new tests, suite 61 -> 74. Fix commit: `5e6fd2c`.
- **Still open:** (a) `README.md`'s results table and section 2 headline
  still quote the 3-policy matrix and must be rewritten around the 5-policy
  one — the honest surviving claim is "beats the industry-standard T+1/T+2/T+3
  schedule 2.85x", NOT "learned when customers have money". (b) `runs/eval.json`
  in the main checkout is stale (3 policies). (c) Whether a model without the
  hardcoded `(1, 2, 7, 8)` flag — forced to learn payday timing from
  `day_of_month` alone — would survive the shift is untested, and is now the
  single most interesting open question in the project. (d)
  `docs/what-broke-essay.md` and `docs/demo-script.md` Beat 3 both quote the
  superseded numbers.

### 2026-09-01 — Removing the hardcoded payday flag did NOT fix the model; the real failure is a two-day near-miss at a step function

- **What happened:** BROKELOG entry 9 blamed `featurize`'s hardcoded
  `day_of_month in (1, 2, 7, 8)` indicator for the learned policy losing to a
  uniform-random control under distribution shift. A de-biased model was
  trained with that feature removed (`payday_flag=False`; `day_of_month`
  retained, so payday timing stays learnable). **It did not fix anything.**
  The hypothesis in entry 9 was wrong, or at best a small part of the story.
- **Evidence:** full 6-policy matrix, seeds `100,101,102`, 500 customers,
  recovered per 1000 failures:
  ```
                             r0_base      r1_shifted    r2_no_signal
  random_in_horizon        182,359.09      220,425.10     118,831.58
  encore_learned           188,259.09      150,291.50     107,677.63
  encore_learned_nopayday  188,259.09      154,867.75     107,411.84
  ```
  De-biasing moved `r1_shifted` from 150,291 to 154,868 -- a 3% gain that
  leaves the model still at 0.70x of random. `r0_base` is unchanged to the
  paisa and `r2_no_signal` is marginally worse. The flag was not the cause.
  Diagnostic that found the real one -- executions by day-of-month in
  `r1_shifted` (salary_days `[3, 10, 25]`, weights `[0.2, 0.3, 0.5]`):
  ```
  encore_learned    day   18  19  20  21  22  23  24  25  26  27  28
                    tried 44  10  37 165  24 219 138  14  56  46  20
                    win%  14%  0%  0%  2%  0%  3%  0%100%100%100%100%

  random_in_horizon tried 42  40  49  39  39  39  63  55  48  38  33
                    win%   5% 10%  2%  3%  0%  0%  0%100%100%100%100%
  ```
- **Root cause:** success is a **step function at day 25**, and the model
  learned the right *region* on the wrong *side* of it. It concentrates 384
  of ~1,064 retries on days 21 and 23 -- two days before salary lands, where
  the observed success rate is 2-3% -- and places only 14 on day 25 itself.
  Summed over days 25-30 (the 100%-success zone) the model lands ~151
  retries against the random control's ~237. That ~86-retry gap, against a
  wall-enforced budget of 3 retries per customer, is the whole 47%
  difference. The failure is therefore not "the model ignores payday" (it
  targets the payday window slightly MORE often than random: 23.9% vs 20.8%
  of retries in days 24-27) but "the model is systematically ~2 days early,
  and earliness at a step function is indistinguishable from being wrong."
  A confident near-miss is worse than no opinion at all, because it spends a
  capped budget on days that are reliably empty while a uniform draw at
  least samples the far side of the cliff.
- **Fix:** none applied. Both models are kept in the matrix
  (`encore_learned`, `encore_learned_nopayday`) so the negative result is
  reproducible rather than quietly dropped. `payday_flag` is a documented
  switch on `featurize`/`generate_training_data`/`LearnedPolicy`, defaulting
  to `True` so previously published numbers stay byte-reproducible (pinned by
  `tests/test_model.py::test_payday_flag_default_is_backward_compatible`).
  Suite 74 -> 76. Fix commit: `2a460a0`.
- **Still open:** (a) **The step function is a simulator artifact and must be
  disclosed as one.** `Portfolio.debit` succeeds deterministically once the
  balance clears, so post-payday success is exactly 100% and pre-payday is
  near 0%. Real balances do not behave like this, and the sharpness of the
  cliff almost certainly overstates how badly a 2-day error would be punished
  in production. The *direction* of the finding is sound; the magnitude is
  simulator-flattered. (b) Why the model settles on days 21-23 specifically
  is not established -- plausibly an r0_base-derived "later in the month is
  better" pattern truncated by the 10-day search horizon, but that is a
  hypothesis, not a measurement. (c) An asymmetric-loss retrain (penalising
  early retries harder than late ones) is the obvious next experiment and has
  not been run. (d) README, `docs/demo-script.md` Beat 3, and
  `docs/what-broke-essay.md` all still quote the superseded 3-policy matrix.

### 2026-09-02 — The control's margin was partly free wins past the end of the simulated month
- **What happened:** While building the day-of-month cliff chart for the web
  site, the `random_in_horizon` series showed a 100% success rate on
  day-of-month 1-5 — the far side of a wrap-around, not the payday window.
  Retries are proposed up to `SEARCH_HORIZON_DAYS = 10` past the failure, but
  `run_cycle(30, ...)` only simulates 30 days, so a late-month failure can be
  retried at an absolute day >= 30. `Portfolio.debit` indexes
  `balance_history[at_hour // 24]` and, when that index is out of range,
  falls back to the live `c.balance_paise` — which at end-of-simulation is
  post-salary-credit and almost always clears the amount. Every retry landing
  past the window is therefore a near-guaranteed success that no policy
  earned. `encore_learned` never proposes into that dead zone; the uniform
  control does, because it draws uniformly over the whole horizon.
- **Evidence:** grouping every `execution` record in `runs/*_audit.jsonl` by
  whether `at_hour // 24 >= 30`:

  ```
  r1_shifted / encore_learned     inside window 1064 won 234 (22.0%)
                                  beyond day 30     0 won   0
  r1_shifted / random_in_horizon  inside window  931 won 313 (33.6%)
                                  beyond day 30    52 won  52 (100.0%)
  ```

  Subtracting only the beyond-window recoveries from each cell's published
  `recovered_per_1000_failures_paise`:

  ```
  cell                            published/1000   free  corrected/1000   drop
  r1_shifted/random_in_horizon      Rs2,20,425.10    52    Rs1,89,186.23  14.2%
  r2_no_signal/random_in_horizon    Rs1,18,831.58    32    Rs1,00,715.79  15.2%
  r2_no_signal/fixed_spread10         Rs81,938.16     3      Rs78,915.79   3.7%
  every other cell (15 of 18)                  --     0               --   0.0%
  ```

  Effect on the two ratios the project reports:

  ```
  regime         random/learned            learned/fixed_t123
  r0_base        0.969 -> 0.969 (no change)   2.767 -> 2.767 (no change)
  r1_shifted     1.467 -> 1.259               2.848 -> 2.848 (no change)
  r2_no_signal   1.104 -> 0.935  (FLIPS)      3.166 -> 3.166 (no change)
  ```

- **Root cause:** two independent gaps that only bite in combination.
  (a) `policies.legal_candidate_hours` clamps candidates to the wall's
  execution window but not to the simulated horizon, so hours past the end of
  the world are legal proposals. (b) `Portfolio.debit` and
  `Portfolio.would_succeed` treat "no balance history for this day" as
  "use the live balance" rather than as "unknown/out of range". The fallback
  was written for far-future queries and is documented as deliberate, but it
  silently converts an out-of-range retry into a free success. The learned
  policy is insulated by accident, not by design: its ranking simply never
  chooses those hours, so the bias lands entirely on the uniform control that
  the whole refutation depends on.
- **Fix:** not yet applied — logged before fixing, per CLAUDE.md. The choice
  between clamping proposals to the simulated horizon, extending
  `balance_history` to cover the full search horizon, and treating
  out-of-range days as a hard failure is a design decision with different
  downstream effects, and it rewrites README, the essay, and the demo script.
- **Still open:** the refutation survives but shrinks and narrows. Random
  still beats the learned policy on the held-out `r1_shifted` by 26% rather
  than 47%, but "beats the model on 2 of 3 regimes" becomes "on 1 of 3" —
  `r2_no_signal` flips to the model by 7%. The claim that never depended on
  this — 2.85x over the industry-standard T+1/T+2/T+3 schedule with zero
  violations in 18 cells — is arithmetically untouched, because neither
  `encore_learned` nor `fixed_t123` scores a single beyond-window win in any
  regime. The four-RNG-stream reproduction in entry 9 (ratios 1.47/1.48/
  1.47/1.51) was measuring the inflated quantity and needs re-running after
  the fix.

### 2026-09-02 — The predicted size of the horizon-clamp correction was wrong by an order of magnitude
- **What happened:** Entry 11 predicted, from a subtraction over the audit
  logs, that clamping retries to the simulated horizon would drop
  `r1_shifted/random_in_horizon` from ₹2,20,425.10 to ₹1,89,186.23 (-14.2%)
  and flip `r2_no_signal` from the control to the model. The clamp was
  implemented and the matrix re-run. Neither happened. The control lost 0.7%
  on `r1_shifted` and 1.3% on `r2_no_signal`, and `r2_no_signal` did not flip.
- **Evidence:** same seeds (100,101,102), same 500 customers, before and after
  the clamp:

  ```
  cell                              pre-clamp        clamped   change
  r0_base/random_in_horizon      Rs1,82,359.09  Rs1,86,900.00    +2.5%
  r1_shifted/random_in_horizon   Rs2,20,425.10  Rs2,18,948.72    -0.7%
  r2_no_signal/fixed_spread10      Rs81,938.16    Rs78,915.79    -3.7%
  r2_no_signal/random_in_horizon Rs1,18,831.58  Rs1,17,259.21    -1.3%
  all 14 other cells                        --             --     0.0%

  regime         random/learned          learned/fixed_t123
  r0_base        0.969 -> 0.993          2.767 -> 2.767
  r1_shifted     1.467 -> 1.457          2.848 -> 2.848
  r2_no_signal   1.104 -> 1.089          3.166 -> 3.166
  ```

  `uv run pytest -q` -> 89 passed. Violations still 0 across all 18 cells.
- **Root cause:** the subtraction treated a beyond-window win as a win that
  would simply disappear. It does not. A retry is a *slot*, not an outcome:
  when the clamp removes the out-of-range hour, the policy proposes an
  in-window hour instead and frequently succeeds there. The wall's 3-retry
  budget is what is scarce, not the individual hour, so the correct
  counterfactual for 52 removed free wins is "52 retries relocated", not "52
  recoveries deleted". `r0_base/random_in_horizon` even went *up* 2.5% — it
  had zero beyond-window executions, so its only change is that the shared
  `random.Random(RANDOM_BASELINE_SEED)` stream is now consumed differently
  once other regimes stop drawing out-of-range hours. Post-hoc subtraction
  over an audit log cannot see either effect; only a re-run can.
- **Fix:** the clamp itself is kept — it is correct on its own merits, since a
  retry past the evaluated period is unobservable and must not be scored. What
  is corrected here is entry 11's **"Still open"** paragraph, which asserted
  the flip as fact. Per CLAUDE.md past entries are never edited, so this entry
  supersedes it. `EVAL_HORIZON_HOURS = 30 * HOURS_PER_DAY` in `evaluate.py`,
  `max_hour` on `legal_candidate_hours` and all five proposing policies, and
  `tests/test_evaluate.py::test_no_policy_executes_past_the_simulated_horizon`
  asserts on the audit log so a future policy bypassing
  `legal_candidate_hours` still trips it. Suite 76 -> 89. Fix commit: `4acb1b2`.
- **Still open:** the headline claims are unchanged and now rest on a scored
  window with no free wins in it. The control still beats the learned policy
  on 2 of 3 regimes (`r1_shifted` 1.46x, `r2_no_signal` 1.09x) and still
  loses narrowly on the regime it trained on (`r0_base` 0.99x). Entry 9's
  four-RNG-stream reproduction has not been re-run against the clamp; the
  main-stream ratio moved only 1.467 -> 1.457, so the conclusion is not in
  doubt, but the specific numbers 1.47/1.48/1.47/1.51 are pre-clamp and
  should be relabelled or regenerated before they are quoted again.

### 2026-09-02 — The insufficient-funds test card fails with error_reason "payment_failed", not "insufficient_funds"
- **What happened:** Razorpay's test-card page lists `4100 2800 0008 0001` as
  the card that declines for insufficient funds. Three test-mode payments made
  with it on Payment Links -- the A0 spike link `plink_TX8TUTJx4sCmkX` and the
  two `encore seed-live` originals for `cust_0005` and `cust_0030` -- all came
  back from `GET /v1/payments` as `status: "failed"`, `error_code:
  "BAD_REQUEST_ERROR"`, `error_source: "gateway"`, `error_step:
  "payment_authorization"`, `error_description: "Payment failed"` and
  `error_reason: "payment_failed"`. The reason string the docs promise never
  appeared. With the two-entry table in `sources.py`
  (`insufficient_funds`, `gateway_technical_error`), all three land in
  `RazorpayFailureSource.unmapped`, and `encore agent --live 3` would have
  parked every real failure as `unmapped_error_reason` and retried nothing.
- **Evidence:** `uv run python scripts/spike_failed_payments.py list`, ~19:00
  IST:

  ```
  {"id": "pay_TXCHLEzZwfcdOY", "status": "failed", "amount": 99900, "method": "card", ..., "error_code": "BAD_REQUEST_ERROR", "error_description": "Payment failed", "error_source": "gateway", "error_step": "payment_authorization", "error_reason": "payment_failed", "notes": {"kind": "original", "cycle_id": "live", "customer_id": "cust_0030"}}
  {"id": "pay_TXCGLl4N2QOjcv", ..., "error_reason": "payment_failed", "notes": {"kind": "original", "cycle_id": "live", "customer_id": "cust_0005"}}
  {"id": "pay_TXCExIcrL6fcrD", ..., "amount": 19900, "error_reason": "payment_failed", "notes": {"cycle_id": "spike", "customer_id": "cust_spike"}}
  ```

  The same listing settled the other A0 question in our favour: the
  `notes` set on each Payment Link arrived on the payment entity intact.
- **Root cause:** on this test account, card declines reach the Payments API
  as one generic gateway authorization failure; the per-reason test cards do
  not surface their reason through `error_reason`. Whether they do on
  Standard Checkout or in live mode was not tested. The mapping table
  assumed the documented string would round-trip.
- **Fix:** `payment_failed` maps to a new soft `DeclineCode.GENERIC_DECLINE`
  -- retryable inside the wall's cap, which is how Razorpay's own T+1/T+2/T+3
  treats any failed subscription charge -- rather than being dropped. The
  simulator never produces it and `model.SOFT_CODES` is untouched, so no
  eval cell moves. Fix commit: `bc69f06`.
- **Still open:** what a real live-mode insufficient-funds decline reports as
  `error_reason` is unverified, so the agent cannot yet tell "no money" from
  "bank said no" on the real rail; README §7 says so.

### 2026-09-02 — Live rehearsal: the link the operator paid was recorded as a timeout, and a retake would have collided at Razorpay
- **What happened:** first live run of `encore agent --live 3 --batch 50
  --speed 6 --timeout 240`. Detection worked (3 real failures found through
  the Payments API, 0 unmapped), the agent created three real recovery links
  (`plink_TXCMK5peBCA4t5`, `plink_TXCMST6ys8Yfga`, `plink_TXCMXbSeoFGj3F`),
  and the batch recovered INR 9,984.00 of INR 28,047.00 on the simulated
  rail. The operator paid `plink_TXCMST6ys8Yfga` (cust_0005, INR 999.00) and
  Razorpay captured it (`pay_TXCQdLbRfAi7lW`) -- but the audit log says
  `outcome: "failure", status: "no_terminal_status_within_timeout"` for all
  three links, and the board showed INR 0.00 recovered on the real rail.
- **Evidence:** Razorpay's own timestamps, fetched afterwards: link created
  19:47:48, payment captured 19:52:00 -- 252 s after creation, against a
  240 s timeout. The agent's polling was correct; the human loop (the link
  URL relayed to the operator, the operator opening it, the mock bank page)
  took four minutes. While planning the retake, a second problem: the live
  failures were given `cycle_id = "live"`, so a retake's attempt_ids -- which
  are the Payment Links' `reference_id`s -- would be identical to the first
  take's (`cust_0005:live:retry:1`). With the ledger kept they are blocked
  locally and no link is created; with a fresh ledger Razorpay rejects the
  duplicate reference_id. Either way the second take cannot run.
- **Root cause:** (1) `--timeout` was sized like a network timeout; it is the
  time a person has to pay. (2) The cycle id for a real failure carried no
  identity of the failure itself.
- **Fix:** `--timeout` defaults to 600 s and every printed link says "pay by
  HH:MM:SS". `RazorpayFailureSource` sets `cycle_id` to the failed payment's
  own id with the `pay_` prefix stripped, so attempt_ids are unique per
  original failure and stay within Razorpay's 40-character reference_id
  limit (pinned by a test). Commit hash backfilled below.
- **Still open:** the video take has to keep the operator's hands on the
  checkout within the window; the demo script says so. The three links from
  this take remain on the account (one paid, two `created`), counted against
  the 30-link test-mode cap.
