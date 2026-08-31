# What broke and how we got out (draft)

This is a draft submission essay assembled only from `BROKELOG.md`'s seven
real, append-only entries. It picks the three deepest of those seven —
judged by how much they changed what the project could actually claim, not
by how much text they took to describe — and walks each one root cause,
evidence, fix, and what is still open, quoting the real commit hashes from
`BROKELOG.md`. Nothing below is invented; every claim traces back to a
`BROKELOG.md` entry or the git history it cites.

## 1. The UPI checkout path the whole plan assumed didn't exist

**Root cause.** The build plan assumed Razorpay's documented test-mode UPI
trick — pay a Payment Link with the VPA `success@razorpay` or
`failure@razorpay` to get a deterministic outcome. That trick simply is not
offered on this account. When the controller opened the two spike checkout
pages in a real browser, checkout showed only Cards, Netbanking, and Wallet
— no UPI tab at all. This isn't a bug anywhere in our code; it's a
platform/account limitation the plan didn't anticipate.

**Evidence.** Manual browser walkthrough of both spike links,
`plink_TWLLefGUFjwjGf` and `plink_TWLLmoEcAAGI4v`
(`docs/spike-notes.md`, "Findings vs. plan assumptions" and "Manual
checkout (browser-driven)"), both showing only Cards/Netbanking/Wallet.

**Fix.** There was no code fix, because there was no bug — the fix was a
documented substitution: use Razorpay's test-mode Netbanking flow instead,
which routes to a simulated bank page with explicit Success/Failure
buttons. That produced `pay_TWLTaB6r7Epvnz` (captured) and
`pay_TWLWl8NzNSEN6q` (failed) in the original spike, and became the
documented mechanism for every later test-mode payment simulation in the
project. Landed in commit `a48b751` ("feat: razorpay client + test-mode
spike notes").

**What's still open.** Whether UPI becomes available on this account later
— after KYC or account activation, say — was never investigated, since
Netbanking already gives a deterministic success/failure repro path and
there was no reason to chase it further. Whether the UPI VPA simulation
needs a different account tier or region setting is also unresearched.

## 2. The labels used to train the model didn't actually vary with time

**Root cause.** `Portfolio.would_succeed(customer_id, at_hour)` — the
function that generated every training label answering "if we retried at
this hour, would it succeed?" — checked the customer's *current* balance
scalar, which by construction reflects the end-of-simulation state
regardless of the `at_hour` argument passed in. The one thing the model was
supposed to learn — *when* to retry — had no timing signal to learn from in
the first place.

**Evidence.** A standalone repro script sampled the same 12 candidate hours
`generate_training_data` uses for five real failures and found every
single one of the 12 hours, spread across a 10-day window with different
days-of-month and hours-of-day, produced the identical label (`unique:
{True}` for `cust_0004`, `cust_0051`, `cust_0109`, `cust_0146`,
`cust_0167`, all insufficient-funds failures).

**Fix.** Commit `62467c0` added a `balance_history` field to `Portfolio`,
snapshotted once per customer per simulated day with no change to RNG
draws, and made `would_succeed` look up the balance as of the queried hour
instead of the live end-of-run scalar. The same commit also fixed two
related defects the same review surfaced: `LearnedPolicy.propose` no
longer proposes hours inside the wall's own cooldown window, and it now
scores every candidate at the fixed `attempt_no=1` the training data
actually used, instead of querying the model out of distribution at
attempt 2 or 3. Measured before/after on the same 300-customer, 3-seed
world: label balance moved from 0.830 (mostly-`True`, time-invariant) to
0.450 (genuinely mixed); holdout accuracy moved from 0.906 to 0.977.

**What's still open.** Nothing, per the entry itself. (Related but
separately documented: `README.md`'s limitations section flags that even
with a real timing signal in the labels, `encore_learned`'s win on the
signal-free `r2_no_signal` regime is likely a search-horizon artifact
rather than learned timing — a distinct, still-open question about the
*evaluation*, not the label-generation bug this entry fixed.)

## 3. The mechanical rail was still blind to time after the oracle was fixed

**Root cause.** Fixing the labeling oracle (above) was not enough, because
the thing every policy is actually scored against — `Portfolio.debit`, via
`SimulatedRail.execute` — had the exact same bug the oracle used to have:
it read the live, end-of-simulation balance scalar regardless of which hour
a retry actually targeted. So which day a policy chose to retry on could
change *how many attempts* it took, but never *whether* the customer was
ultimately recoverable, which collapsed any real timing difference between
policies down to zero on the metric that matters — recovered money.

**Evidence.** `runs/eval.json` showed `recovered_per_1000_failures_paise`
bit-for-bit identical between `fixed_t123` and `encore_learned` in all
three regimes (r0_base 18825909 vs 18825909; r1_shifted 27981242 vs
27981242; r2_no_signal 13668289 vs 13668289). A diagnostic script
confirmed this wasn't a rounding artifact: for all 9 (regime, seed) cells
the two policies recovered the identical customer set for the identical
total paise, even though the specific attempt hours used were almost
always different — in `r1_shifted` seed 100, all 156 matched successful
customers used a different `at_hour`, and only 5 of 156 even landed in the
same day-bucket.

**Fix.** This one reversed a plan simplification that had been
user-approved earlier ("per-failure processing is not a correctness
issue") — the controller ruled that reversal was the correct call once the
symptom was traced to its actual mechanism. Commit `869cdcf` made
`Portfolio.debit` consult the same `balance_history` the oracle already
used, mirroring `would_succeed`'s day-lookup pattern exactly, so the rail
and the labeling oracle finally agree on the one axis the whole eval
harness exists to measure: whether timing matters.

**What's still open.** Nothing, per the entry itself. One dependent
consequence did surface afterward: pre-fix `--dry-run` evidence quoted in
an earlier task report went stale the moment this landed, because it had
replayed each retry at the exact hour the original debit had already
failed — which the now-time-aware rail is guaranteed to re-fail, every
time. That was caught, diagnosed, and fixed separately (commit `7c0b956`,
moving the demo's replay hour to failure-hour +72), and is its own,
fourth `BROKELOG.md` entry — not folded into this one, because it was a
distinct failure with its own root cause (a downstream consumer's stale
assumption, not a repeat of this bug).

## On the discipline itself

Every one of `BROKELOG.md`'s seven entries was written *before* the fix,
not after — that ordering is the whole point. `CLAUDE.md`'s rule is
explicit: append an entry the moment a test fails for an unpredicted
reason, a bug turns up in code believed done, a design decision gets
reversed, or an external API behaves differently than documented — and
write the entry before touching the fix, then come back and fill in the
commit hash once it lands. That ordering is what makes the log worth
reading: it isn't a curated highlight reel written in hindsight to make
the debugging look cleaner than it was, it's a running record of what was
actually true at the moment something broke, including the wrong guesses
about UPI simulation, the plan's own test-arithmetic errors, and a
correctness bug that survived one full round of "believed done" code
review before a second pass caught it. Entries are never edited after the
fact, so the record of being wrong stays in the file next to the record of
getting it right.
