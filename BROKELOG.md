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
