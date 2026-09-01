# Demo script

Rehearsable, timed script for the submission video. Every command below is
one that actually ran during this build — see `BROKELOG.md` and
`docs/spike-notes.md` for the verbatim transcripts each beat is drawn from.
Total runtime budget: **under 5:00**. Terminal-on-screen budget: **under
90 seconds total**, itemized per beat below. Both budgets carry slack —
they are not run right up to the limit.

Metrics are quoted **only** from the held-out eval seeds `100, 101, 102`
(`n_customers=500` each) — that is all `runs/eval.json` contains; the model
itself was trained on a disjoint seed range (`1`–`5`, regime `r0_base`
only), per `README.md` section 2.

| Beat | Window | Duration | Terminal time |
|---|---|---:|---:|
| 1. The problem | 0:00–0:20 | 20s | 0s |
| 2. Tests are the floor | 0:20–1:00 | 40s | 15s |
| 3. The scoreboard | 1:00–2:10 | 70s | 20s |
| 4. The wall is the star | 2:10–2:55 | 45s | 10s |
| 5. Real rail | 2:55–4:35 | 100s | 35s |
| 6. The honest close | 4:35–4:55 | 20s | 0s |
| **Total** | | **295s (4:55)** | **80s** |

5 seconds of runtime slack, 10 seconds of terminal-time slack against the
5:00 / 90s caps.

---

## Beat 1 — The problem (0:00–0:20, 20s, 0s terminal)

One breath, no terminal on screen — talking head or title card over the
README's framing (section 1, "The problem"):

> UPI AutoPay mandates fail at a rate that would be a P0 outage anywhere
> else — NPCI data reported via Business Standard puts revocations at
> 20M+ mandates cancelled a month, mostly over low balances, and Mint
> reports an August 2025 execution failure rate of 55–90% across banks.
> NPCI also caps how you're allowed to react: one original execution plus
> three retries, only in non-peak windows. Encore is a policy layer for
> that narrow, rule-bound retry budget — recover what the rule allows,
> refuse everything it doesn't, never the reverse.

## Beat 2 — Tests are the floor (0:20–1:00, 40s, 15s terminal)

Command (run live, ~10 seconds to execute):

```
uv run pytest -q
```

Expected on-screen result — re-measured after the horizon-matched-baseline
work (BROKELOG 9 and 10) took the suite from 61 to 76:

```
76 passed in 10.54s
```

Wall-clock varies with venv warmth; a cold run that has to build the venv
first is slower. Do one throwaway run before recording so the take is warm.

Say while the dots scroll: "76 tests, green, in seconds. 24 of those live
in `tests/test_wall.py` alone — that's the compliance wall's adversarial
suite, and it's the file we come back to in a minute. Another 13 are in
`tests/test_policies.py`, and those exist to prove our own baseline is
*fair* — that the control searches the identical candidate set the model
does, so we can't accidentally rig the comparison in our favour."
(Confirmed independently: `uv run pytest tests/test_wall.py -q` →
`24 passed in 0.04s`; `tests/test_policies.py -q` → `13 passed in 1.09s`.)

## Beat 3 — The scoreboard, and the experiment that undercut it (1:00–2:10, 70s, 20s terminal)

**Pre-bake this before recording** — the eval now runs 6 policies x 3
regimes x 3 seeds at 500 customers (54 world simulations) and takes several
minutes. Do not run it live. Show the command, say "pre-baked," cut to the
output:

```
uv run encore eval --seeds 100,101,102 --customers 500
```

Then run the fast one live (~1 second), which reads the pre-baked
`runs/eval.json` and writes `runs/scoreboard.html`:

```
uv run encore report
```

Open it in a browser. **Do not lead with the learned policy.** Lead with
the control — it is the more interesting number and a judge will find it
anyway:

- `encore_learned` recovers ₹1,50,291.50 per 1000 failures on `r1_shifted`
  against `fixed_t123`'s ₹52,774.63 — **2.85x the industry-standard
  schedule**, which is the claim that survives.
- `random_in_horizon` — the same retry budget, the same candidate hours,
  picked **at random** — recovers **₹2,20,425.10**. Say it out loud:
  *"random beats our model by 47% on the held-out regime, using fewer
  attempts. We built that control ourselves, and it's in the repo."*
- **Violations: `0` in every one of the 18 regime x policy cells, each
  aggregated over 3 seeds (54 runs).** Then the caveat, unprompted: "that's
  a post-hoc replay through the wall — it can't re-check cooldown from the
  audit log alone, because the log doesn't record a sequence's previous
  attempt hour. Cooldown is enforced live. The caveat is in the README, not
  hidden."

If there is time, land the mechanism — it is the best 15 seconds in the
video. Success in `r1_shifted` is a step function at day 25:

```
encore_learned    day   21  22  23  24  25  26  27
                  tried 165  24 219 138  14  56  46
                  win%    2%  0%  3%  0%100%100%100%
```

*"The model isn't missing payday — it's aiming at it and landing two days
early, every time. With only three retries allowed per customer, two days
early is the same as completely wrong. We thought a hardcoded feature was
the cause, removed it, retrained — and we were wrong about that too. Both
are in BROKELOG, entries 9 and 10, written before either fix."*

## Beat 4 — The wall is the star (2:10–2:55, 45s, 10s terminal)

Open `tests/test_wall.py` and scroll briefly to the precedence block
(`test_precedence_killed_beats_hard_decline`,
`test_precedence_hard_decline_beats_cap`,
`test_precedence_hard_decline_beats_cooldown`,
`test_precedence_hard_decline_beats_window`,
`test_precedence_cap_beats_cooldown`,
`test_precedence_cap_beats_window`,
`test_precedence_cooldown_beats_window`) — read one or two names aloud, not
the full bodies.

Say: "Every one of these is adversarial on purpose — they exist to prove a
fixed precedence order: killed beats hard-decline beats retry-cap beats
cooldown beats execution-window. `wall.py` is a pure function — no I/O, no
clock, no randomness, no model call, enforced by project rule. The ML
proposes an hour. It never gets a vote on whether that hour is legal. The
ML cannot override this wall — it proposes, the wall disposes."

Optional terminal beat (10s): re-run `uv run pytest tests/test_wall.py -q`
live to show `24 passed in 0.03s` again as the camera holds on the file.

## Beat 5 — Real rail (2:55–4:35, 100s, 35s terminal)

**Revised after re-verification.** The previous version of this beat used
`--n 4`. That command now creates **zero** payment links: `runs/demo_ledger.txt`
contains exactly the four `reference_id`s that `--n 4` covers, so every one
is skipped as an already-executed ledger hit and there is nothing to pay on
camera. Enumerated against the live ledger and the seed-100 kill set:

```
  n= 1  cust_0113  INR   999.00  LEDGER-HIT (skipped, no link)
  n= 2  cust_0403  INR   199.00  LEDGER-HIT + WALL-DENIED sequence_killed
  n= 3  cust_0092  INR   999.00  LEDGER-HIT (skipped, no link)
  n= 4  cust_0417  INR   199.00  LEDGER-HIT + WALL-DENIED sequence_killed
  n= 5  cust_0447  INR   199.00  FRESH -> creates a REAL payment link
  n= 6  cust_0140  INR   199.00  FRESH -> creates a REAL payment link
  n= 7  cust_0182  INR   499.00  FRESH -> creates a REAL payment link
```

**Polling is sequential, one link at a time, each for the full `--timeout`**
(`poll_until_terminal`, called in a plain `for` loop over `created` in
`demo.py`). An unpaid link never leaves `created` status, so it always runs
the clock out. Creating 7 links and paying 1 means the other 6 time out
*back to back* — at `--timeout 240` that is 24 minutes of dead terminal.
Create exactly one link.

| `--n` | Ledger hits | Real links created | Verdict |
|---|---:|---:|---|
| 4 | 4 | **0** | Broken — nothing to pay |
| **5** | 4 | **1** | **Use this.** Poll ends the moment you pay. |
| 6 | 4 | 2 | Second link burns a full timeout |
| 12 | 4 | 7 | ~24 min of dead air |

Split the beat in two: the wall refusing money costs nothing and is the
stronger visual, so it goes first and off the network.

### Beat 5a — the wall refuses money (free, instant, no network)

```
rm -f runs/demo_ledger_dryrun.txt && uv run python -m encore.demo --dry-run --n 8
```

**The `rm` is required.** The dry-run keeps its *own* ledger
(`runs/demo_ledger_dryrun.txt`, written because `run_demo_slice` appends a
`_dryrun` suffix), and it accumulates across rehearsals exactly like the
real one. A second dry run without deleting it prints nothing but skip
lines. This file is local scratch containing no real `reference_id`s, so
deleting it is safe and should be done before **every** take.

Verified output — 6 links, 2 refusals, in under a second:

```
[2] cust_0403:demo_s100:retry:1: wall denied (sequence_killed) -- skipping, no link created.
[4] cust_0417:demo_s100:retry:1: wall denied (sequence_killed) -- skipping, no link created.
```

Say: "Two of these customers replied CANCEL. The wall denied them *before*
a link was ever created — the model proposed, the wall refused, and no
money was ever requested."

### Beat 5b — the real rail (exactly one live link)

```
PYTHONUNBUFFERED=1 uv run python -m encore.demo --n 5 --timeout 120
```

`PYTHONUNBUFFERED=1` matters — without it, buffered stdout can hide the
printed payment-link URLs until the process exits.

Expect four ledger-hit lines, then one fresh link for `cust_0447` at
₹199.00. **Narrate the four skips as the idempotency guarantee firing
live** — "already executed, no new link created" is exactly what
`AttemptLedger.already_executed` exists to produce, and this is it running
on camera rather than in a test.

Then, in the browser:

1. Open the printed `https://rzp.io/rzp/...` link.
2. Enter contact number **9123456789** when checkout prompts for a mobile
   number (an all-same-digit number like `9999999999` is rejected
   server-side — don't use one on camera).
3. Choose **Netbanking** (NOT UPI — this account's checkout offers no UPI
   method at all; see `BROKELOG.md`'s first entry), then the mock bank
   **BOB**.
4. Click **Success**. The poller returns `status=paid outcome=success` on
   its next 5-second tick — no waiting out the timeout.
5. Open the **Razorpay test dashboard** and show the payment as captured —
   the evidence that this went through a real Razorpay API call, not a
   simulator.

**Never delete `runs/demo_ledger.txt`.** Its four `reference_id`s are
permanently consumed at Razorpay; deleting the file makes the code
re-attempt them and the API will reject the reuse mid-recording. To get
more fresh links, raise `--n` instead.

**On the failure case — cite it, don't film it.** A failed payment does
**not** move a link's `status` out of `created`; `created` is
indistinguishable from "nobody tried yet" through the polling API
(`docs/spike-notes.md`, "Key finding for Task 11's polling design").
`poll_until_terminal` therefore runs the full timeout before classifying it
as `no_terminal_status_within_timeout` — correct behavior, not a hang, but
minutes of screen time. Quote the recorded line from the original live run
instead:

```json
{"event": "execution", "customer_id": "cust_0417", "attempt_id": "cust_0417:demo_s100:retry:1", "reference_id": "cust_0417:demo_s100:retry:1", "link_id": "plink_TWNaJA6Iehrx7c", "amount_paise": 19900, "status": "created", "outcome": "no_terminal_status_within_timeout", "rail": "razorpay_test_mode"}
```

from `runs/demo_audit.jsonl` — say: "that line was recorded by a real run,
off-camera, so you don't have to watch four minutes of polling." Note that
`cust_0417` is now in the kill set, so the *current* code denies it at the
wall before creating a link; the quoted line is historical evidence from
the original run, not something `--n 5` reproduces today.

## Beat 6 — The honest close (4:35–4:55, 20s, 0s terminal)

No terminal. Talking head or title card:

> Every failure while building this is in `BROKELOG.md` — ten entries,
> append-only, written before the fix, not after. The last two are the ones
> that matter: we built the control that could kill our own headline, it
> did, and then our explanation for why was wrong too. Read `README.md`'s
> limitations section for what this can't prove: no UPI checkout path on
> this test account, a violations count that can't re-verify cooldown from
> the audit log alone, and a step function in the simulator that makes our
> own headline finding look sharper than production would. What survives is
> the wall and a 2.85x beat on the industry-standard schedule. What doesn't
> is the claim that the ML earned it. This is modeled on NPCI's publicly
> reported retry rules, with citations. We never claim compliant.
