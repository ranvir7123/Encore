import os
import time

import httpx

BASE = "https://api.razorpay.com/v1"

# Terminal statuses per the payment_links resource. docs/spike-notes.md's key
# finding (Task 2 spike): a FAILED payment attempt does NOT move a link's
# status off "created" -- amount_paid stays 0 and payments[] stays empty.
# Razorpay's payment_links endpoint has no "failed" terminal status; "created"
# is not evidence of "nobody has tried yet," only "paid" is a reliable
# positive signal. Task 11's poll_until_terminal is designed around this.
TERMINAL_STATUSES = {"paid", "cancelled", "expired"}


class RazorpayClient:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        auth = (os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"])
        # transport is injected only by tests (httpx.MockTransport); production
        # leaves it None and httpx picks its default network transport.
        self._http = httpx.Client(base_url=BASE, auth=auth, timeout=20.0, transport=transport)

    def create_payment_link(self, amount_paise: int, description: str, reference_id: str,
                            notes: dict[str, str] | None = None) -> dict:
        body: dict = {
            "amount": amount_paise,
            "currency": "INR",
            "description": description,
            "reference_id": reference_id,
        }
        if notes:
            # notes ride along onto the payment entity itself (verified in
            # docs/spike-notes.md, A0), which is how a failed payment is
            # correlated back to a customer without a webhook.
            body["notes"] = notes
        resp = self._http.post("/payment_links", json=body)
        resp.raise_for_status()
        return resp.json()

    def fetch_payment_link(self, link_id: str) -> dict:
        resp = self._http.get(f"/payment_links/{link_id}")
        resp.raise_for_status()
        return resp.json()

    def list_payments(self, from_ts: int, to_ts: int, count: int = 100, skip: int = 0) -> list[dict]:
        """GET /v1/payments in a Unix-time window. Failed attempts DO appear here
        with status="failed" and an error_reason -- unlike a Payment Link's own
        payments[] array, which only ever lists captured payments
        (docs/spike-notes.md, A0). Returns the unwrapped `items` list."""
        resp = self._http.get("/payments", params={"from": from_ts, "to": to_ts,
                                                   "count": count, "skip": skip})
        resp.raise_for_status()
        return resp.json().get("items", [])


def poll_until_terminal(client, link_id: str, timeout_s: int = 300, interval_s: int = 5) -> str:
    """Poll `client.fetch_payment_link(link_id)` until status is in
    TERMINAL_STATUSES, or timeout_s elapses -- returns the final observed
    status either way (never raises on timeout).

    `client` is duck-typed to anything exposing `fetch_payment_link(link_id)
    -> dict` (a `status` key is all that's read) -- both `RazorpayClient` and
    `encore.demo.SimulatedRazorpayClient` satisfy this, so Task 11's
    `--dry-run` path exercises this exact function, not a stand-in.

    Because a failed attempt never produces a "failed" status (see
    TERMINAL_STATUSES' docstring above), a poll against a genuinely-failed
    payment will never see a terminal status and this function will run until
    timeout_s and return the last observed status (typically "created") --
    that is the intended, documented behavior for Task 11's failure-link
    case, not a bug: the caller (encore.demo.run_demo_slice) is responsible
    for recording that as a distinct "no_terminal_status_within_timeout"
    outcome rather than treating it as either success or failure.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        status = client.fetch_payment_link(link_id)["status"]
        if status in TERMINAL_STATUSES or time.monotonic() >= deadline:
            return status
        time.sleep(interval_s)
