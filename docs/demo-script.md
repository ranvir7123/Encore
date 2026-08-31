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

Command (run live, ~4 seconds to execute):

```
uv run pytest -q
```

Expected on-screen result — the real output, captured just before writing
this script:

```
............................................................             [100%]
60 passed in 3.64s
```

Say while the dots scroll: "60 tests, green, in seconds. 24 of those live
in `tests/test_wall.py` alone — that's the compliance wall's adversarial
suite, and it's the file we come back to in a minute." (Confirmed
independently: `uv run pytest tests/test_wall.py -q` → `24 passed in 0.03s`.)

## Beat 3 — The scoreboard (1:00–2:10, 70s, 20s terminal)

**Pre-bake this before recording** — the eval run takes several minutes for
1,500 simulated customers across 3 regimes x 3 policies x 3 seeds. Do not
run it live. Show the command on screen, say "pre-baked," and cut to the
already-produced output:

```
uv run encore eval --seeds 100,101,102 --customers 500
```

Say: "This is the real command — I ran it before recording because it
takes a few minutes, not because it's hiding anything. Here's what it
wrote." Then run the fast one live (~1 second):

```
uv run encore report
```

This reads the pre-baked `runs/eval.json` and writes `runs/scoreboard.html`.
Open it in a browser and show:

- The metrics table (same numbers as `README.md` section 2): `encore_learned`
  recovering ₹1,88,259.09 per 1000 failures in `r0_base` against
  `fixed_t123`'s ₹68,040.91 and `immediate_x3`'s ₹0.00, with
  `recovery_per_attempt_paise` favoring `encore_learned` in every regime.
- The **violations row: `0` in every one of the 9 (regime, policy, seed)
  cells.** Say explicitly: "zero violations, but that's a post-hoc replay
  through the wall — it can't re-check cooldown from the audit log alone,
  because the log doesn't record a sequence's previous attempt hour. That
  caveat is in the README, not hidden."

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

**Before recording:** either leave `runs/demo_ledger.txt` in place (it
already exists from prior runs) or raise `--n` past however many
`reference_id`s have already been consumed on this Razorpay test account.
Each `attempt_id` becomes a real, unique `reference_id` the first time it's
used — Razorpay itself refuses to reuse one cleanly, and the local ledger
will block a repeat before that even matters. **A ledger-skip line during
the recording is not a failure — narrate it as proof of the idempotency
guarantee** ("already executed, no new link created" is the same behavior
`AttemptLedger.already_executed` is designed to produce, live, not just in
a test).

Command (this is the exact command that produced the transcript in
`docs/spike-notes.md`, "Task 11 live demo run"):

```
PYTHONUNBUFFERED=1 uv run python -m encore.demo --n 4 --timeout 240
```

`PYTHONUNBUFFERED=1` matters — without it, buffered stdout can hide the
printed payment-link URLs until the process exits.

Walk through the on-screen output as it prints: customer id, amount, and a
`https://rzp.io/rzp/...` link for each fresh (non-ledger-hit) attempt.

For each live link, in the browser:

1. Open the link.
2. Enter contact number **9123456789** when checkout prompts for a mobile
   number (an all-same-digit number like `9999999999` is rejected
   server-side — don't use one on camera).
3. Choose **Netbanking**, then the mock bank **BOB**.
4. On the mock bank page, click **Success** for the link you want to pay,
   or **Failure** for the one you want to deliberately fail.
5. After the Success click, open the **Razorpay test dashboard** and show
   the payment as captured — the real evidence that this went through an
   actual Razorpay API call, not a simulator.

**Timing budget for the failure case, by design, not a bug:** a failed
payment attempt does **not** move the link's `status` out of `created` —
`created` is indistinguishable from "nobody tried yet" from the polling API
alone (`docs/spike-notes.md`, "Key finding for Task 11's polling design").
`poll_until_terminal` therefore runs the **full 240-second timeout** for
any failed link before classifying it as
`no_terminal_status_within_timeout`, and that classification is correct,
not a hang. Budget for it: either (a) let the failure link's poll run out
on camera — it costs real screen minutes and does not fit inside this
beat's 100-second window if shown in full, so prefer (b) — demo the
**success link live**, and cite the recorded audit line for the timeout
case instead:

```json
{"event": "execution", "customer_id": "cust_0417", "attempt_id": "cust_0417:demo_s100:retry:1", "reference_id": "cust_0417:demo_s100:retry:1", "link_id": "plink_TWNaJA6Iehrx7c", "amount_paise": 19900, "status": "created", "outcome": "no_terminal_status_within_timeout", "rail": "razorpay_test_mode"}
```

from `runs/demo_audit.jsonl` — say: "that line was recorded by the exact
same run, off-camera, so you don't have to watch four minutes of polling."

## Beat 6 — The honest close (4:35–4:55, 20s, 0s terminal)

No terminal. Talking head or title card:

> Every failure while building this is in `BROKELOG.md` — seven entries,
> append-only, written before the fix, not after. Read `README.md`'s
> limitations section for what this can't prove: no UPI checkout path on
> this test account, a violations count that can't re-verify cooldown from
> the audit log alone, and an `r2_no_signal` win that's likely a search-
> horizon artifact, not learned timing. This is modeled on NPCI's publicly
> reported retry rules, with citations. We never claim compliant.
