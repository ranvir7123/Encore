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
