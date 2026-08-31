import os

import httpx

BASE = "https://api.razorpay.com/v1"


class RazorpayClient:
    def __init__(self) -> None:
        auth = (os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"])
        self._http = httpx.Client(base_url=BASE, auth=auth, timeout=20.0)

    def create_payment_link(self, amount_paise: int, description: str, reference_id: str) -> dict:
        resp = self._http.post("/payment_links", json={
            "amount": amount_paise,
            "currency": "INR",
            "description": description,
            "reference_id": reference_id,
        })
        resp.raise_for_status()
        return resp.json()

    def fetch_payment_link(self, link_id: str) -> dict:
        resp = self._http.get(f"/payment_links/{link_id}")
        resp.raise_for_status()
        return resp.json()
