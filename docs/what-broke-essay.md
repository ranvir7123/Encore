# What broke: four times we measured the wrong thing

Assembled only from `BROKELOG.md`'s ten real, append-only entries, each
written before its fix and carrying the commit hash that closed it. Nothing
here is reconstructed in hindsight.

Encore is a retry sequencer for failed UPI AutoPay debits. A pure-function
compliance wall decides **whether** a retry is legal; a policy chooses
**when**, inside it. Every serious bug we hit had the same shape, and it was
never the shape we expected: **the code was fine and the measurement was
broken.** Four times we believed a number, went looking at how it was
produced, and found the instrument bent. The fourth time, fixing the
instrument told us our own centrepiece doesn't work — and that entry is in
the repo too.

## 1. The training labels had no timing signal in them

The model's entire job is to learn *when* to retry. Its labels came from
`Portfolio.would_succeed(customer_id, at_hour)` — "if we retried at this
hour, would it clear?" That function read the customer's *current* balance
scalar, which by construction held the end-of-simulation state no matter
what `at_hour` you passed.

A repro script sampled the same 12 candidate hours the training pipeline
uses, for five real failures, spread across a 10-day window with different
days-of-month and hours-of-day. Every one of the 12 returned the identical
label — `unique: {True}` for all five customers.

The model was scoring 0.906 holdout accuracy while being *structurally
incapable* of learning the one thing it existed to learn. It had found some
other correlation, and we had congratulated it.

Commit `62467c0` gave `Portfolio` a `balance_history`, snapshotted once per
customer per simulated day with no change to RNG draws, and made
`would_succeed` read the balance as of the queried hour. Label balance moved
from 0.830 — overwhelmingly `True`, because it was answering a question
about end-state — to 0.450. Holdout accuracy moved from 0.906 to 0.977.

**A high score is not evidence. It is a claim about a measurement, and the
measurement is the thing to audit.**

## 2. Then the rail couldn't see time either

Fixing the labels was not enough, because the thing every policy is scored
*against* — `Portfolio.debit` — had the same defect. The oracle now knew
that Tuesday differs from Friday. The rail still did not. So a policy could
choose a genuinely better hour and be scored as though it had chosen nothing
at all.

This one had been reviewed and explicitly waved through as "a documented
simplification, not a correctness issue." That judgement was wrong, and it
was reversed only after tracing the mechanism end to end rather than
re-reading the note. Commit `869cdcf` made the rail time-aware.

It also invalidated evidence elsewhere: the demo replayed retries at the
exact hour they had already failed, which against a time-aware rail
deterministically re-fails forever — 0 of 32 succeeded. That is a separate
entry, found because a later pass re-checked the demo's evidence against the
current code instead of trusting it.

**A shared dependency can invalidate a file that nothing edited.**

## 3. The comparison was rigged — by omission

With the instrument fixed, the numbers looked good: `encore_learned`
recovered 2.85x what `fixed_t123` did on the held-out regime. `fixed_t123`
is Razorpay's real T+1/T+2/T+3 shape, so this was a fair-sounding fight.

It was not a fair fight. `LearnedPolicy` searches a **10-day** candidate
window and starts past the wall's cooldown so its proposals never get
denied. `fixed_t123` sees **three days** and does neither. Search *width*
and ranking *quality* were bundled into one number, and every multiple we
had reported silently contained both.

So we built the control that could kill the claim. `random_in_horizon` draws
its retry hour **uniformly at random** from the identical candidate set the
model ranks, from the identical starting hour — enforced by a test asserting
the two policies share the same function *object*, not merely equal
behaviour, so the control cannot quietly drift into being unfair to itself.

On `r1_shifted`, the held-out regime the headline came from:

| Policy | Recovered / 1000 failures |
|---|---:|
| `fixed_t123` (industry standard) | ₹52,774.63 |
| `fixed_spread10` (dumb, no model) | ₹143,001.35 |
| **`random_in_horizon` (control)** | **₹220,425.10** |
| `encore_learned` | ₹150,291.50 |

**Random beat the trained model by 47%, using fewer attempts** — ~1,327
against ~1,436 per 1000 failures, so not a brute-force win. Reproduced across
four independent RNG streams (1.47, 1.48, 1.47, 1.51). A dumb T+3/T+6/T+9
heuristic with no model at all reaches 2.71x. Most of our headline was
reachable with no learning whatsoever. Commit `5e6fd2c`.

## 4. And our explanation for that was wrong too

The obvious culprit was a feature in `model.featurize`:
`day_of_month in (1, 2, 7, 8)`, commented "near-payday flag." A hardcoded
human prior, tuned to the training regime, where 90% of customers are paid on
day 1 or 7. Under shift, half are paid on day 25. Clean story.

We removed it, retrained, and reran. It moved `r1_shifted` from ₹1,50,291.50
to ₹1,54,867.75 — still 0.70x of random. **The story was wrong.**

So we stopped theorising and measured where the retries actually land.
Success in that regime is a step function at day 25:

```
encore_learned    day   21  22  23  24  25  26  27
                  tried 165  24 219 138  14  56  46
                  win%    2%  0%  3%  0%100%100%100%
```

The model is not missing payday. It targets that window slightly *more* often
than random does. It is aiming at the cliff and landing **two days short,
every time** — 384 retries on days 21 and 23, fourteen on day 25. Against a
wall-enforced budget of three retries per customer, those two days are the
entire 47%.

**A confident near-miss is worse than no opinion at all**, because it spends
a capped budget on days that are reliably empty, while a uniform draw at
least samples the far side. Commit `2a460a0`.

That same entry discloses what would have been convenient to leave out: the
step function is a **simulator artifact**. `Portfolio.debit` succeeds
deterministically once the balance clears, so 100%-after and 0%-before is
sharper than any real bank. The direction holds; the magnitude is flattered
by our own simulator. Why the model settles on days 21–23 specifically is
still unestablished, and an asymmetric-loss retrain has not been run.

## What survives

The compliance wall: a pure function — no I/O, no clock, no randomness, no
model call — with 24 adversarial tests pinning a fixed precedence order, and
zero violations across all 18 evaluated cells. The 2.85x beat over the
industry-standard retry schedule, which is real and is what a merchant would
actually feel. A working sequencer that is genuinely better than what ships
today.

What does not survive is the claim that the machine learning earned it.

## On the discipline

Every entry was written *before* its fix, then returned to for the commit
hash. That ordering is the whole point: the log is not a curated highlight
reel written in hindsight, it is a record of what was true at the moment
something broke — including the wrong guesses, the plan's own arithmetic
errors, and a correctness bug that survived a full "believed done" review.
Entries are never edited. The record of being wrong stays in the file next to
the record of getting it right.

We could have shipped the 2.85x and said nothing. The control that refutes it
is code we wrote ourselves, on purpose, knowing what it might cost. An
experiment that cannot embarrass you is not an experiment.
