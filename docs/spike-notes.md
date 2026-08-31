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
