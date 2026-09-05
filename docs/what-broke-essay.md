# What broke: eight times the instrument, the API, or the human was not what we assumed

Assembled only from `BROKELOG.md`'s fifteen real, append-only entries, each
written before its fix and carrying the commit hash that closed it. Nothing
here is reconstructed in hindsight.

Encore is a recovery agent for failed UPI AutoPay debits. A pure-function
compliance wall decides **whether** a retry is legal; a policy chooses
**when**, inside it; the agent detects failures on Razorpay, nudges, reads
the reply, collects on a real Payment Link, and reports. Every serious bug
we hit had the same shape, and it was never the shape we expected: **the
code was fine and something we had trusted was not.** First the
measurement, four times. Then the platform, once. Then the human in the
loop, twice. And once, our own prediction of what a fix would do.

## 1. The training labels had no timing signal in them

The model's entire job is to learn *when* to retry. Its labels came from
`Portfolio.would_succeed(customer_id, at_hour)`. That function read the
customer's *current* balance scalar, which by construction held the
end-of-simulation state no matter what `at_hour` you passed. A repro
sampled the 12 candidate hours the training pipeline uses for five real
failures: every one returned the identical label. The model was scoring
0.906 holdout accuracy while being structurally incapable of learning the
one thing it existed to learn. Commit `62467c0` gave the portfolio a
per-day `balance_history`.

**A high score is not evidence. It is a claim about a measurement, and the
measurement is the thing to audit.**

## 2. Then the rail couldn't see time either

The thing every policy is scored *against*, `Portfolio.debit`, had the same
defect. A policy could choose a genuinely better hour and be scored as if it
had chosen nothing. This had been reviewed and waved through as "a
documented simplification"; it was reversed only after tracing the
mechanism end to end. Commit `869cdcf`. It also silently invalidated the
demo's evidence, which replayed retries at the exact hour they had failed.

**A shared dependency can invalidate a file that nothing edited.**

## 3. The comparison was rigged, by omission

With the instrument fixed, `encore_learned` recovered 2.85x what
`fixed_t123` (Razorpay's real T+1/T+2/T+3) did on the held-out regime. It
was not a fair fight: the model searched a 10-day window, the baseline saw
three days. So we built the control that could kill the claim:
`random_in_horizon`, the identical candidate set and starting hour, the hour
drawn uniformly at random, enforced by a test that the two policies share
the same function *object*.

**Random beat the trained model by 47%, using fewer attempts.** A dumb
T+3/T+6/T+9 heuristic reached 2.71x with no learning at all. Commit
`5e6fd2c`.

## 4. And our explanation for that was wrong too

The obvious culprit was a hardcoded `day_of_month in (1, 2, 7, 8)`
"near-payday" feature. We removed it, retrained, reran: 0.70x of random,
still. Measuring where retries actually land found the cause. Success in
that regime is a step function at day 25; the model puts 384 retries on
days 21 and 23 and fourteen on day 25. It aims at payday and lands two
days short, every time. Commit `2a460a0`.

**A confident near-miss is worse than no opinion**, because it spends a
capped budget on days that are reliably empty.

## 5. The control had free wins past the end of the month, and the fix did a tenth of what we predicted

While charting that cliff for the site, the random control showed a 100%
success rate on days 1–5: retries proposed past day 30 fell off the end of
the simulated month into a fallback that read the post-salary balance.
Subtracting those wins from the audit log predicted the control would drop
14% and one regime would flip to the model. We clamped retries to the
window and reran. The control moved 0.7%. Nothing flipped.

A retry is a *slot*, not an outcome: remove the out-of-range hour and the
policy proposes an in-window one instead, and often wins there. The
wall's three-retry budget is what is scarce, not any particular hour.
Post-hoc arithmetic over a log cannot see that; only a rerun can. Commits
`4acb1b2` and the entry that corrects the earlier entry's "Still open".

**When you predict what a fix will do, write the prediction down before
running it. Ours was off by an order of magnitude, and that is in the log.**

## 6. The documented test card does not report its reason

Razorpay's test-card page lists a card that declines for insufficient
funds. Three real test-mode payments made with it came back through the
Payments API as the generic `error_reason: "payment_failed"`, gateway,
authorization step. Our two-entry mapping table would have parked every
real failure as an unclassifiable exception and retried nothing. The
string now maps to a retryable generic decline, which is how Razorpay's own
retry schedule treats any failed charge; anything else stays unmapped and
is reported, never guessed. Commit `bc69f06`. The same listing settled a
question in our favour: notes set on a Payment Link do arrive on the
payment, which is how a real failure finds its customer without a webhook.

## 7. The paid link that timed out

First live rehearsal. Detection worked, three real recovery links were
created, and the operator paid one. Razorpay captured it 252 seconds after
the link was created; the agent had stopped polling at 240 and recorded a
timeout. The polling was correct. The timeout had been sized like a network
timeout when it was really the time a person has to open a page and click
through a mock bank. While planning the retake we found the second half:
the live failures shared one cycle id, so a retake's reference ids would
have collided at Razorpay. The failed payment's own id is the cycle id now,
the timeout is ten minutes, and every printed link says when it expires.
Commit `a57463c`.

## 8. The customer paid the original, and the agent could not see it

Second rehearsal. Detection worked again, one recovery link was created,
and the operator paid — on the original link they had failed a minute
earlier. Razorpay captured ₹299 for that customer; the agent, watching only
its own link, timed out again. That is not an operator error a real system
gets to blame the customer for: paying the original demand after a nudge
is the most ordinary outcome of dunning, and Stripe's and Chargebee's stop
the retry schedule the moment the invoice is paid. Ours now does too. A
capture watch polls the Payments API for a captured payment carrying the
customer's notes, ends the sequence as recovered, and books it as
"paid on their own". The two checkout pages now announce which is which
in their first words. Commit `d884508`.

The third rehearsal landed: one real failed debit detected, one real
recovery link created by the agent, paid inside the window, booked as
`outcome: success, status: paid`. It is in `docs/evidence/`.

## What survives

The compliance wall: a pure function with 24 adversarial tests pinning a
fixed precedence order, zero violations across all 32 evaluated cells. An
agent that runs the whole loop on Razorpay's real rail for a live slice and
on the simulator for the batch, through one wall, one ledger and one audit
log. A shipped policy with no model in it — the parsed promise when there
is one, a uniform draw inside the compliant window otherwise — that
recovers 4.4x what the industry schedule does on the held-out regime, where
the promise signal is worth about 5% against a 2–3% noise floor that we
report next to it.

What does not survive is the claim that the machine learning earned any of
it. The model ties the random control on the regime it trained on and
loses under shift. Building the control was the most useful thing we did.

## On the discipline

Every entry was written *before* its fix, then returned to for the commit
hash. The log holds the wrong guesses, the plan's own arithmetic errors, a
correctness bug that survived a "believed done" review, a prediction that
missed by 10x, and two rehearsals that recovered nothing on the real rail.
Entries are never edited. The record of being wrong stays in the file next
to the record of getting it right.

We could have shipped the model's 2.85x and said nothing. The control that
refutes it is code we wrote ourselves, on purpose, knowing what it might
cost. An experiment that cannot embarrass you is not an experiment.
