# Submission checklist

Short reference for the buildathon form. Everything below traces to a real
repo artifact: `README.md`, `BROKELOG.md`, `docs/spike-notes.md`,
`docs/evidence/`. Nothing here is invented.

## Form fields

- **Track:** AI Revenue Recovery
- **Project name:** Encore
- **What it solves (one paragraph):** Failed UPI AutoPay and card e-mandate
  debits churn silently, and NPCI caps how a merchant may react (one
  execution plus three retries, non-peak windows). Encore is a recovery
  agent for that budget: it detects failed payments on Razorpay, decides
  inside a pure-function compliance wall, nudges, reads the customer's
  reply, collects on a real Payment Link, and books every rupee on a live
  board with an exception list. The shipped policy has no model; it
  recovers 4.4x what Razorpay's documented T+1/T+2/T+3 schedule does on the
  held-out regime with zero compliance violations in all 32 evaluated cells.
  We also trained a timing model, built the control that refutes it, and
  report that it earns nothing.
- **Repo URL:** https://github.com/ranvir7123/Encore
- **Video link:** TODO(user) — record from `docs/demo-script.md`, upload
  unlisted, paste here.
- **What broke, and how you got out:** paste `docs/what-broke-essay.md`,
  trimmed to the field's limit. If the limit is tight, keep sections 3, 4,
  7 and 8 and the closing two paragraphs.

## The in-person round, if shortlisted

Say these unprompted; each is verifiable by reading one file.

- The wall is a pure function (`src/encore/wall.py`), 24 adversarial tests
  pin a fixed precedence order, and the language model never gets a vote on
  legality. Open the file.
- The control experiment: `random_in_horizon` shares the model's candidate
  function by *identity* (`tests/test_policies.py`), beat the model by 46%
  under shift, and the model ties it in-distribution. Then the mechanism:
  the model lands two days before the day-25 cliff.
- The shipped policy has no model, and why: `promise_aware_random`, 4.4x
  over T+1/2/3, with the promise's 5% read against a 3% noise floor between
  random streams.
- The live rail: one real failed debit detected through `GET /v1/payments`,
  one real recovery link created by the agent and paid, booked as `status:
  paid` (`docs/evidence/agent-audit-2026-09-02.jsonl`). And that it took
  three takes: the 240-second timeout (entry 14) and the customer paying
  the original link (entry 15), which became the self-cure watch.
- Where AI is not used, and the one place it belongs: reading the customer.
  Measured 2026-09-05 on 40 labeled Hinglish replies: keyword 27/40 with 0 of
  6 disputes and three disputes misread as promises to pay; Haiku 4.5 37/40;
  Sonnet 5 40/40. Getting there took an identity-linked key, a workspace
  header, and a fenced-JSON bug the silent fallback would have hidden
  (entry 16). The agent takes the parser as a flag.
- Money is integer paise everywhere; the only floats are display.

## The 6/12-month answer

Concrete, each a named gap in the repo, not a roadmap slogan.

- **Grow the reply set past 40 rows and price the parser.** Sonnet 5 is
  40/40 on the labeled set; the next questions are how it holds on a few
  hundred real replies, what a classification costs per reply, and whether
  a `dispute` should route to a human queue rather than a park.
- **Live-mode error reasons.** Test mode reports every card decline as
  `payment_failed`; the mapping table needs live data to tell "no money"
  from "bank said no", which is the difference between a retry and a park.
- **A real reply channel.** The customer's reply is simulated today. The
  parser and the promise path are channel-agnostic; Telegram's Bot API
  needs no public URL and would make the loop real end to end.
- **Subscriptions, not links.** Razorpay test mode can force a subscription
  charge to fail from the dashboard; wiring `subscription.pending` into the
  failure source puts the agent on the actual recurring-debit object.
- **Self-cure on the real rail.** Unit-tested, not yet observed live; the
  next rehearsal should pay the original on purpose.
- **Cancel abandoned links.** A recovery link that self-cures stays
  `created` on the account; the agent should cancel it.
