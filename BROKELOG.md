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
  commit `<fill after commit — see below>`.
- **Still open:** Whether UPI becomes available on this account later (e.g.
  after KYC/activation) is unknown and was not investigated further, since
  Netbanking already provides a deterministic success/failure repro path.
  Also open: whether Razorpay's UPI VPA test simulation requires a
  different account tier/region setting — not researched, out of scope for
  this spike.
