"""A0 spike: can we DETECT a failed test-mode payment, with its reason, via the
Payments API -- and does a Payment Link's `notes.customer_id` reach the payment?

    uv run python scripts/spike_failed_payments.py create   # prints a link URL
    uv run python scripts/spike_failed_payments.py list     # failed payments, last 3h

Fail the link on checkout with the insufficient-funds test card
4100 2800 0008 0001 (any CVV, any future expiry), then run `list`.
"""
import json
import sys
import time

from dotenv import load_dotenv

from encore.razorpay_client import RazorpayClient


def main() -> None:
    load_dotenv()
    client = RazorpayClient()
    mode = sys.argv[1] if len(sys.argv) > 1 else "create"
    if mode == "create":
        ref = f"spike-notes-{int(time.time())}"
        resp = client._http.post("/payment_links", json={
            "amount": 19900, "currency": "INR",
            "description": "Encore A0 spike: failed-payment detection",
            "reference_id": ref,
            "notes": {"customer_id": "cust_spike", "cycle_id": "spike"},
        })
        resp.raise_for_status()
        link = resp.json()
        print("created:", link["id"], link["status"], link["short_url"])
        print("reference_id:", ref)
        print("notes on link:", json.dumps(link.get("notes")))
    elif mode == "list":
        to_ts = int(time.time())
        from_ts = to_ts - 3 * 3600
        resp = client._http.get("/payments", params={"from": from_ts, "to": to_ts, "count": 100})
        resp.raise_for_status()
        items = resp.json().get("items", [])
        print(f"payments in window: {len(items)}")
        for p in items:
            keep = {k: p.get(k) for k in (
                "id", "status", "amount", "method", "order_id", "created_at",
                "error_code", "error_description", "error_source", "error_step",
                "error_reason", "notes", "description")}
            print(json.dumps(keep, ensure_ascii=False))
    else:
        raise SystemExit("usage: create | list")


if __name__ == "__main__":
    main()
