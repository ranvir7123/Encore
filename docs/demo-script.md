# Demo script

Rehearsable, timed script for the 5-minute submission video. Every command
below has actually run; the transcripts they are drawn from are in
`docs/spike-notes.md` (takes 1–3) and `docs/evidence/`. Runtime budget
**under 5:00**. Rehearse the real-rail beat once before recording: two of
three rehearsals failed on the human step, and both failures are in
`BROKELOG.md` (entries 14 and 15).

| Beat | Window | What is on screen |
|---|---|---|
| 1. The problem | 0:00–0:20 | title card |
| 2. The loop, no network | 0:20–1:20 | terminal + board |
| 3. The real rail | 1:20–3:30 | terminal + checkout + board |
| 4. The wall and the control | 3:30–4:25 | tests + table |
| 5. What broke | 4:25–4:50 | BROKELOG |

## Before recording

- `.env` has the Razorpay **test** keys. Payment Links are capped at 30 per
  test account; this build has used 17. A take uses 2.
- A warm venv: run `uv run pytest -q` once off camera.
- `uv run encore eval` has been run (`runs/eval.json` exists) if you want to
  open the scoreboard; the README table is the same numbers.
- Keep ONE browser window with the Razorpay checkout ready. Do the real-rail
  beat in one sitting: the pay window is 10 minutes and the detection window
  is 20 minutes.

## Beat 1 — The problem (0:00–0:20)

> UPI AutoPay mandates fail at a rate that would be a P0 outage anywhere
> else: NPCI data reported via Mint put the August 2025 execution failure
> rate at 55 to 90 percent across banks, and 20 million mandates a month get
> revoked, mostly over low balances. NPCI also caps how you may react: one
> original execution plus three retries, in non-peak windows. Encore is an
> agent for that budget. It detects the failure, nudges, reads the reply,
> retries inside the rules, and books the money.

## Beat 2 — The loop, no network (0:20–1:20)

```
rm -f runs/agent_ledger_dryrun.txt runs/agent_audit_dryrun.jsonl
uv run encore agent --dry-run --batch 50 --speed 0
```

It finishes in seconds. Open `runs/board_dryrun.html`. Read the cards aloud:
at risk, recovered, attempts, nudges and replies. Then the two small tables:

> Wall denials are the compliance gate saying no: hard declines, cancelled
> customers. Parked is the exception list: what the agent will not chase,
> and why. Thirteen revoked mandates, four customers who replied "cancel",
> nineteen where the policy ran out of legal slots. Every line here is an
> audit record, not a summary.

Run it again without deleting the ledger. `attempts 0`, `duplicates_blocked`
non-zero:

> Same ledger, second run: nothing executes twice. That is the idempotency
> guarantee, on camera.

## Beat 3 — The real rail (1:20–3:30)

Say up front:

> Now the same loop with one real customer on Razorpay test mode. Nothing
> is mocked here except the customer's reply.

```
uv run encore seed-live --n 1
```

It prints one link titled **FAIL THIS ONE**. Open it, contact `9123456789`,
Cards, `4100 2800 0008 0001`, any CVV and expiry, Failure if a mock page
appears. Show "Payment failed". Close the tab. (15 seconds.)

```
PYTHONUNBUFFERED=1 uv run encore agent --live 1 --batch 50 --speed 6 --window-s 1200
```

First line: `Payments API: 1 mapped failure(s), 0 unmapped, in the last 20 min.`

> That failure was found through Razorpay's Payments API, with a reason
> code, and correlated to the customer by the notes the original link
> carried. No webhook.

Within about 40 seconds it prints one line:
`LINK for cust_XXXX INR 999.00: https://rzp.io/... (plink_...) pay by HH:MM:SS`

> The agent chose the hour inside the wall's window, the wall allowed it,
> and it created a real Payment Link. This page is titled PAY THIS ONE. The
> other one said FAIL THIS ONE. Rehearsal two, I paid the wrong one, and
> the agent learned to notice that too. Entry 15.

Open the link, contact `9123456789`, **Netbanking**, bank **BOB**, **Success**.
Switch to `runs/board.html` (it refreshes itself every 3 seconds): the
customer's row turns to `recovered`, rail `razorpay_test_mode`, status
`paid`, and the Recovered card moves by ₹999.

> That is a real Razorpay payment id behind that row. The other fifty are
> the simulator; same wall, same ledger, same audit log.

If the link does not appear within a minute, keep talking through the
board; it is the batch working. Do not restart: a restart with the same
ledger executes nothing new, by design.

## Beat 4 — The wall and the control (3:30–4:25)

```
uv run pytest tests/test_wall.py -q
```

`24 passed`. Open `tests/test_wall.py` at the precedence block and read two
names.

> Killed beats hard-decline beats retry-cap beats cooldown beats window.
> The wall is a pure function, no I/O, no clock, no randomness, by project
> rule. The policy proposes; the wall disposes. The language model never
> touches it.

Open the README table, point at four rows of `r1_shifted`:

> Industry standard, T+1/2/3: ₹52,774 per thousand failures. Our trained
> model: ₹1,50,291. Then the control we built to kill our own claim: the
> same window, hours picked at random: ₹2,18,948. Random beat the model by
> 46 percent, and we found out why: it aims at payday and lands two days
> early, every time. So the model does not ship. What ships is the random
> policy plus the customer's own promise: ₹2,30,673. Four point four times
> the industry schedule, and the promise is worth about five percent over
> random, which we report next to a three percent noise floor.

## Beat 5 — What broke (4:25–4:50)

Scroll `BROKELOG.md`.

> Fifteen entries, append-only, each written before its fix with the commit
> that closed it. The instrument was wrong four times. The platform did not
> match its docs once. Our prediction of a fix was off by ten times. And
> the human in the loop broke the live demo twice before it landed. What
> survives is the wall, an agent that runs on the real rail, and a policy
> with no model in it that beats the industry schedule four times over.
> What does not survive is the claim that the machine learning earned any
> of it. That control is code we wrote ourselves, on purpose.

End on the board.
