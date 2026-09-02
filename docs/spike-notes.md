# Razorpay test-mode spike notes

Date: 2026-08-31

## What was run

1. `uv run python scripts/spike.py` — creates payment link `spike-001` (amount
   50000 paise = INR 500.00, description "Encore spike: can we create
   links?"), then fetches it back.

2. A one-off `uv run python -c "..."` invocation (not saved as a script) to
   create a second payment link `spike-002` (same amount, description
   "Encore spike: failure path") for the failure@razorpay manual test in
   Step 3 of the brief:

   ```python
   from dotenv import load_dotenv
   load_dotenv()
   from encore.razorpay_client import RazorpayClient

   c = RazorpayClient()
   link = c.create_payment_link(50000, "Encore spike: failure path", "spike-002")
   print("created:", link["id"], link["status"], link["short_url"])
   print("fetched:", c.fetch_payment_link(link["id"])["status"])
   ```

3. A follow-up `uv run python -c "..."` to fetch the full JSON body of the
   first link (`plink_TWLLefGUFjwjGf`) for documentation, via
   `c.fetch_payment_link(...)`.

## Verbatim output

### Step 1: `uv run python scripts/spike.py`

```
created: plink_TWLLefGUFjwjGf created https://rzp.io/rzp/4Jnj8Fz
fetched: created
```

### Step 2: second link (spike-002)

```
created: plink_TWLLmoEcAAGI4v created https://rzp.io/rzp/UB30CgC
fetched: created
```

### Full JSON of the first payment link (`fetch_payment_link`)

```json
{
  "accept_partial": false,
  "allow_full_payment": false,
  "amount": 50000,
  "amount_paid": 0,
  "cancelled_at": 0,
  "created_at": 1788171977,
  "currency": "INR",
  "customer": {},
  "description": "Encore spike: can we create links?",
  "expire_by": 0,
  "expired_at": 0,
  "first_min_partial_amount": 0,
  "id": "plink_TWLLefGUFjwjGf",
  "notes": null,
  "notify": {
    "email": false,
    "sms": false,
    "whatsapp": false
  },
  "payment_plan": false,
  "payments": [],
  "reference_id": "spike-001",
  "reminder_enable": false,
  "reminders": {
    "status": "failed"
  },
  "short_url": "https://rzp.io/rzp/4Jnj8Fz",
  "status": "created",
  "updated_at": 1788171977,
  "upi_link": false,
  "user_id": "",
  "whatsapp_link": false
}
```

## Payment links created

| reference_id | link id | short URL | status at creation | status after checkout attempt |
|---|---|---|---|---|
| spike-001 | `plink_TWLLefGUFjwjGf` | https://rzp.io/rzp/4Jnj8Fz | `created` | `paid` |
| spike-002 | `plink_TWLLmoEcAAGI4v` | https://rzp.io/rzp/UB30CgC | `created` | `created` (payment attempt failed, link itself stayed `created`) |

## Manual checkout (browser-driven)

Performed by the controller, driving a real browser against the two short
URLs above.

- **spike-001 (plink_TWLLefGUFjwjGf): PAID.** Method: Netbanking. Payment id
  `pay_TWLTaB6r7Epvnz`. Checkout showed "Payment successful ₹500". Aug 31
  2026 ~16:03 IST.
- **spike-002 (plink_TWLLmoEcAAGI4v): FAILED.** Method: Netbanking. Payment
  id `pay_TWLWl8NzNSEN6q`. Checkout showed "Payment failed ₹500". Aug 31
  2026 ~16:06 IST.

### Re-fetch after checkout — verbatim

Command:

```python
from dotenv import load_dotenv
load_dotenv()
import json
from encore.razorpay_client import RazorpayClient

c = RazorpayClient()
for lid in ["plink_TWLLefGUFjwjGf", "plink_TWLLmoEcAAGI4v"]:
    link = c.fetch_payment_link(lid)
    print("---", lid, "---")
    print(json.dumps(link, indent=2))
```

Output:

```json
--- plink_TWLLefGUFjwjGf ---
{
  "accept_partial": false,
  "allow_full_payment": false,
  "amount": 50000,
  "amount_paid": 50000,
  "cancelled_at": 0,
  "created_at": 1788171977,
  "currency": "INR",
  "customer": {},
  "description": "Encore spike: can we create links?",
  "expire_by": 0,
  "expired_at": 0,
  "first_min_partial_amount": 0,
  "id": "plink_TWLLefGUFjwjGf",
  "notes": null,
  "notify": {
    "email": false,
    "sms": false,
    "whatsapp": false
  },
  "order_id": "order_TWLNKtHSBal9IA",
  "payment_plan": false,
  "payments": [
    {
      "amount": 50000,
      "created_at": 1788172448,
      "method": "netbanking",
      "payment_id": "pay_TWLTaB6r7Epvnz",
      "status": "captured"
    }
  ],
  "reference_id": "spike-001",
  "reminder_enable": false,
  "reminders": {
    "status": "failed"
  },
  "short_url": "https://rzp.io/rzp/4Jnj8Fz",
  "status": "paid",
  "updated_at": 1788172448,
  "upi_link": false,
  "user_id": "",
  "whatsapp_link": false
}
--- plink_TWLLmoEcAAGI4v ---
{
  "accept_partial": false,
  "allow_full_payment": false,
  "amount": 50000,
  "amount_paid": 0,
  "cancelled_at": 0,
  "created_at": 1788171984,
  "currency": "INR",
  "customer": {},
  "description": "Encore spike: failure path",
  "expire_by": 0,
  "expired_at": 0,
  "first_min_partial_amount": 0,
  "id": "plink_TWLLmoEcAAGI4v",
  "notes": null,
  "notify": {
    "email": false,
    "sms": false,
    "whatsapp": false
  },
  "order_id": "order_TWLUEy8iUzEv1M",
  "payment_plan": false,
  "payments": [],
  "reference_id": "spike-002",
  "reminder_enable": false,
  "reminders": {
    "status": "failed"
  },
  "short_url": "https://rzp.io/rzp/UB30CgC",
  "status": "created",
  "updated_at": 1788172464,
  "upi_link": false,
  "user_id": "",
  "whatsapp_link": false
}
```

**Key finding for Task 11's polling design:** after a *failed* payment
attempt, the payment link's own `status` field does **not** move to a
terminal "failed" state — it stays `created`, with `amount_paid: 0` and an
empty `payments` array. Razorpay does record the failed attempt as its own
object (`order_id: order_TWLUEy8iUzEv1M` was created, and a payment id
`pay_TWLWl8NzNSEN6q` exists), but it never showed up in the payment link's
`payments` list on fetch, and the top-level `status` never left `created`.
A poller watching only `payment_links.status` cannot distinguish "nobody
has tried to pay yet" from "someone tried and failed" — both look like
`created`. Task 11 needs to account for this: `created` is not evidence of
"no attempt happened," only `paid` is a reliable positive signal from this
endpoint. If failed-attempt detection matters, a different signal (the
Payment entity via webhook, or fetching the order/payments directly) is
required — the payment link resource alone will not surface it.

By contrast, the *successful* payment link (spike-001) picked up an
`order_id` and a `payments` array entry with `status: "captured"`, and the
top-level `status` correctly moved to `paid` with `amount_paid` matching
the link amount.

## Findings vs. plan assumptions

- **UPI is NOT available on this test account's Payment Links checkout —
  contradicts the plan.** The plan assumed a `success@razorpay` /
  `failure@razorpay` UPI VPA flow (per Razorpay's documented test-mode UPI
  simulation). In practice, the checkout page for both links only offered
  **Cards, Netbanking, and Wallet** as payment methods — no UPI option
  appeared at all. This is the first BROKELOG entry (see BROKELOG.md).
  Outcomes were instead driven via **Netbanking**, which routes to
  Razorpay's simulated/mock bank page in test mode. That mock bank page
  presents explicit **"Success" and "Failure" buttons** — clicking one
  deterministically produces a captured or failed payment. This is the
  practical substitute for the UPI VPA trick described in the plan, and is
  what Task 10/11 should rely on for any future manual or scripted
  test-mode payment simulation.
- **Checkout requires a contact mobile number before it will show payment
  methods.** This field is validated server-side: an obviously-fake
  all-same-digit number (`9999999999`) was rejected. A different
  fictitious-but-valid-shaped number, `9123456789`, was accepted and let
  checkout proceed. Not mentioned anywhere in the plan. Anything that
  scripts or automates checkout (not currently in scope) needs to account
  for this required field and its validation.
- A **Cards** payment method field is also present on checkout (not just
  Netbanking/Wallet) but was not exercised in this spike — noted for
  completeness in case Task 11 wants a card-based repro path instead of
  netbanking.
- Aside from the UPI gap, the plan's core assumption held: Payment Links
  can be created and fetched in test mode with no feature flags, using
  plain basic-auth httpx calls against `https://api.razorpay.com/v1`. No
  401s, no "feature not enabled" errors on the API side.
- `create_payment_link` and `fetch_payment_link` worked exactly as written
  in the brief, verbatim code, no modifications needed.
- One minor thing not mentioned in the plan: the fetched link body includes
  a `reminders.status: "failed"` field even though `reminder_enable` is
  `false` and no reminder was ever attempted, on both links, before and
  after checkout. This looks like a Razorpay default/no-op value rather
  than a real failure — worth treating with suspicion if reminders are
  ever used, but it does not block anything for Task 2 or Task 10. Not
  filing a separate BROKELOG entry for this: nothing broke, nothing
  contradicted a documented behavior we relied on, it's just an
  unexplained default value in a field we don't use.
- `amount` round-trips as integer paise as expected. `reference_id`
  round-trips correctly, which Task 10/11 will need to reconcile
  webhook/poll results back to internal state.

## Open questions for Task 11

- Does the Razorpay webhook for `payment_link.paid` / `payment.failed`
  fire reliably where the polling `status` field does not distinguish a
  failed attempt from no attempt? This spike only exercised polling via
  `fetch_payment_link`, not webhooks.
- Should Task 11 poll the underlying order/payments instead of (or in
  addition to) the payment link status, given the `created`-stays-`created`
  behavior on failure observed above?

## Task 11 live demo run

Date: 2026-08-31 (same day, later). Command run by the controller:

```
PYTHONUNBUFFERED=1 uv run python -m encore.demo --n 4 --timeout 240
```

Full terminal transcript, verbatim:

```
=== Encore demo slice ===
seed=100 regime=r0_base n_requested=4 n_available=4

[1] cust_0113:demo_s100:retry:1: already executed (ledger hit) -- skipping, no new link created.
[2] cust_0403:demo_s100:retry:1: already executed (ledger hit) -- skipping, no new link created.
[3] cust_0092:demo_s100:retry:1
    amount: INR 999.00 (99900 paise)
    link:   https://rzp.io/rzp/QEEb5kcT
[4] cust_0417:demo_s100:retry:1
    amount: INR 199.00 (19900 paise)
    link:   https://rzp.io/rzp/h7uDrXhc

(operator instructions omitted)

Polling 2 link(s) (timeout=240s, interval=5s each)...

cust_0092:demo_s100:retry:1: status=paid outcome=success
cust_0417:demo_s100:retry:1: status=created outcome=no_terminal_status_within_timeout
```

Resulting `runs/demo_audit.jsonl`, verbatim (4 lines):

```json
{"event": "duplicate_blocked", "attempt_id": "cust_0113:demo_s100:retry:1", "reference_id": "cust_0113:demo_s100:retry:1"}
{"event": "duplicate_blocked", "attempt_id": "cust_0403:demo_s100:retry:1", "reference_id": "cust_0403:demo_s100:retry:1"}
{"event": "execution", "customer_id": "cust_0092", "attempt_id": "cust_0092:demo_s100:retry:1", "reference_id": "cust_0092:demo_s100:retry:1", "link_id": "plink_TWNaIZxUaf4nl8", "amount_paise": 99900, "status": "paid", "outcome": "success", "rail": "razorpay_test_mode"}
{"event": "execution", "customer_id": "cust_0417", "attempt_id": "cust_0417:demo_s100:retry:1", "reference_id": "cust_0417:demo_s100:retry:1", "link_id": "plink_TWNaJA6Iehrx7c", "amount_paise": 19900, "status": "created", "outcome": "no_terminal_status_within_timeout", "rail": "razorpay_test_mode"}
```

### What happened, link by link

- `[1]` `cust_0113:demo_s100:retry:1` and `[2]` `cust_0403:demo_s100:retry:1`
  were **skipped** — `AttemptLedger.already_executed` hit, because these two
  reference_ids were already created and recorded during an earlier aborted
  dry-run-adjacent invocation of `encore.demo` (the one used for Task 11's own
  code-review/verification pass, against the *real* ledger file
  `runs/demo_ledger.txt`, not the `_dryrun` one). No new Payment Link was
  created for either; only `duplicate_blocked` audit records were appended.
- `[3]` `cust_0092:demo_s100:retry:1` — link `plink_TWNaIZxUaf4nl8`
  (`https://rzp.io/rzp/QEEb5kcT`, ₹999). Controller paid it via the Netbanking
  mock bank page, clicking **Success** (payment id `pay_TWNc61563OZWxl`). The
  poller correctly resolved `status=paid outcome=success`.
- `[4]` `cust_0417:demo_s100:retry:1` — link `plink_TWNaJA6Iehrx7c`
  (`https://rzp.io/rzp/h7uDrXhc`, ₹199). Controller deliberately failed it via
  the Netbanking mock bank page, clicking **Failure** (payment id
  `pay_TWNdukJdEe4NmX`). The link's status never left `created` — exactly the
  behavior this spike document predicted above ("Key finding for Task 11's
  polling design"). `poll_until_terminal` ran for the full `--timeout 240`
  seconds, then correctly returned the last observed status (`created`)
  instead of hanging or crashing; `run_demo_slice` classified this as
  `outcome="no_terminal_status_within_timeout"`, a distinct record from both
  `success` and a hypothetical `failure`. Exit code 0.

### Observations

1. **Ledger-hit skipping was demonstrated live, not just in the dry-run
   verification.** Links `[1]`/`[2]` were the byproduct of an earlier,
   separately-aborted invocation against the real (non-`_dryrun`) ledger.
   Rather than creating two brand-new real Payment Links (and burning two
   more never-reusable `reference_id`s — see note below), the idempotency
   check in `run_demo_slice` correctly recognized both `attempt_id`s as
   already-executed and skipped link creation, appending
   `duplicate_blocked` records instead. This is the real-rail proof of the
   same behavior Task 11's `--dry-run` re-run test demonstrated in
   isolation: the `AttemptLedger` check protects the live rail exactly as
   designed, without needing a special-case for "real vs. simulated."
2. **The failure link behaved exactly as the Task 2 spike predicted.**
   `plink_TWNaJA6Iehrx7c`'s status never left `created` after the operator
   deliberately clicked Failure on Razorpay's mock bank page — `amount_paid`
   stayed effectively unpaid and no terminal status (`paid`/`cancelled`/
   `expired`) was ever produced by the API, matching `spike-002`'s
   (`plink_TWLLmoEcAAGI4v`) behavior from the original Task 2 spike above.
   `outcome="no_terminal_status_within_timeout"` is therefore the *correct*
   record for this case — not a bug, not an ambiguous result — and is exactly
   the outcome Task 11's design (see `task-11-report.md`) was built to
   produce instead of a false `"failure"` classification or an infinite hang.

### Notes for any future on-camera rerun

- **Buffered stdout hides the printed URLs when output is redirected or
  captured** (e.g. piped to a file, or captured by a recording tool that
  doesn't allocate a real TTY) — Python buffers stdout differently for a pipe
  than for an interactive terminal, and the numbered-list URLs are the first
  thing printed. Run with `PYTHONUNBUFFERED=1` (as done above) or in a real
  console window so URLs appear immediately rather than only at process exit
  or not at all if the process is killed mid-run.
- **Each `reference_id` is consumed forever on this Razorpay account** — once
  an `attempt_id` has been used to create a real Payment Link, Razorpay itself
  (not just the local `AttemptLedger`) has recorded that `reference_id`
  against a real link; nothing observed in this spike suggests Razorpay would
  accept creating a second link with the same `reference_id` cleanly, and in
  any case the local ledger will block the attempt first (as demonstrated
  above). A fresh on-camera run should therefore either (a) leave
  `runs/demo_ledger.txt` intact and treat any ledger-hit skips as
  demo-worthy proof of idempotency (as this run did for `[1]`/`[2]`), or (b)
  pass a higher `--n` so it reaches past the already-consumed reference_ids
  into fresh soft-decline failures instead of re-colliding with them.

## A0 spike — failed-payment detection through the Payments API (2026-09-02)

Question: can a FAILED test-mode attempt be detected programmatically, with a
reason, and does a Payment Link's `notes.customer_id` reach the payment?
Script: `scripts/spike_failed_payments.py` (`create` / `list`).

First link (`plink_TX8I88IJxQ3hq5`, notes `{"customer_id": "cust_spike",
"cycle_id": "spike"}`) was paid successfully by the operator by mistake --
which still answered the notes question. Verbatim `list` output:

```
payments in window: 1
{"id": "pay_TX8RaULODLixB9", "status": "captured", "amount": 19900, "method": "card", "order_id": "order_TX8QOOjvBqq5W6", "created_at": 1788344874, "error_code": null, "error_description": null, "error_source": null, "error_step": null, "error_reason": null, "notes": {"cycle_id": "spike", "customer_id": "cust_spike"}, "description": "#TX8I88IJxQ3hq5"}
```

Second link (`plink_TX8TUTJx4sCmkX`) and the two `encore seed-live` originals
were failed on checkout with the documented insufficient-funds test card
`4100 2800 0008 0001`. Verbatim `list` output:

```
payments in window: 3
{"id": "pay_TXCHLEzZwfcdOY", "status": "failed", "amount": 99900, "method": "card", "order_id": "order_TXCGgUGCz4B3lK", "created_at": 1788358378, "error_code": "BAD_REQUEST_ERROR", "error_description": "Payment failed", "error_source": "gateway", "error_step": "payment_authorization", "error_reason": "payment_failed", "notes": {"kind": "original", "cycle_id": "live", "customer_id": "cust_0030"}, "description": "#TX8vAnO2Xx6zTv"}
{"id": "pay_TXCGLl4N2QOjcv", "status": "failed", "amount": 99900, "method": "card", "order_id": "order_TXCFg3iP9Ei8r6", "created_at": 1788358322, "error_code": "BAD_REQUEST_ERROR", "error_description": "Payment failed", "error_source": "gateway", "error_step": "payment_authorization", "error_reason": "payment_failed", "notes": {"kind": "original", "cycle_id": "live", "customer_id": "cust_0005"}, "description": "#TX8v9sXKb4xC1e"}
{"id": "pay_TXCExIcrL6fcrD", "status": "failed", "amount": 19900, "method": "card", "order_id": "order_TXCEIgRCesxblI", "created_at": 1788358243, "error_code": "BAD_REQUEST_ERROR", "error_description": "Payment failed", "error_source": "gateway", "error_step": "payment_authorization", "error_reason": "payment_failed", "notes": {"cycle_id": "spike", "customer_id": "cust_spike"}, "description": "#TX8TUTJx4sCmkX"}
```

Findings:

1. **Failed attempts DO appear in `GET /v1/payments`** with `status: "failed"`
   and error fields, the surface the Payment Link's own `payments[]` never
   shows (it lists captured payments only). Detection needs no webhook.
2. **Notes propagate** from the Payment Link to the payment entity, intact.
   That is how a real failure is correlated back to a customer.
3. **The documented insufficient-funds card does not report
   `insufficient_funds`.** All three declines came back as the generic
   `error_reason: "payment_failed"`, `error_source: "gateway"`, `error_step:
   "payment_authorization"`. BROKELOG entry 13; `sources.py` maps that string
   to the retryable `DeclineCode.GENERIC_DECLINE`.

## Live rehearsal, take 1 (2026-09-02, ~19:47 IST)

```
rm -f runs/agent_ledger.txt runs/agent_audit.jsonl runs/board.html
PYTHONUNBUFFERED=1 uv run encore agent --live 3 --batch 50 --speed 6 --timeout 240 --interval 5
```

Verbatim transcript:

```
Payments API: 3 mapped failure(s), 0 unmapped, in the last 180 min.
=== Encore recovery agent ===
seed 100 | regime r1_shifted | 50 simulated + 3 live on Razorpay test mode | policy promise_aware_random | 6.0 sim-hours per second | live
board: runs\board.html

  LINK for cust_0030 INR 999.00: https://rzp.io/rzp/axKqebU  (plink_TXCMK5peBCA4t5)
  LINK for cust_0005 INR 999.00: https://rzp.io/rzp/fUMEFUGD  (plink_TXCMST6ys8Yfga)
  LINK for cust_spike INR 199.00: https://rzp.io/rzp/4UZ06Sh  (plink_TXCMXbSeoFGj3F)

at risk     INR 28,047.00
recovered   INR 9,984.00  (35.6%)
attempts 87  denied 17  nudges 53  duplicates_blocked 0
parked: hard_decline_terminal=14, policy_stop=20, sequence_killed=3
audit: runs\agent_audit.jsonl  ledger: runs\agent_ledger.txt  board: runs\board.html
```

Audit counts: 200 decisions, 53 nudges, 10 replies (6 cancel, 4 promise),
87 executions (16 successes, all on the simulated rail), 37 parks, 3 links.
The operator paid `plink_TXCMST6ys8Yfga`; Razorpay captured
`pay_TXCQdLbRfAi7lW` at 19:52:00, 252 s after the link was created at
19:47:48 -- 12 s after the agent's 240 s timeout had already recorded
`no_terminal_status_within_timeout`. Every rupee on the board came from the
simulator. BROKELOG entry 14: the timeout was sized for software, and the
live `cycle_id` would have made a second take's reference_ids collide.
Kept under `runs/take1/`.
