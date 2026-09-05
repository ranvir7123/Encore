"""RazorpayClient is a thin httpx wrapper; these tests pin the two things the
agent depends on -- the Payments-API window query and notes on Payment Links --
against an httpx.MockTransport, so no network and no real reference_id is
consumed."""
import json

import httpx
import pytest

from encore.razorpay_client import RazorpayClient


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")


def test_list_payments_sends_the_window_and_unwraps_items(keys):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"entity": "collection", "count": 1,
                                         "items": [{"id": "pay_1", "status": "failed"}]})

    client = RazorpayClient(transport=httpx.MockTransport(handler))
    assert client.list_payments(100, 200) == [{"id": "pay_1", "status": "failed"}]
    assert "from=100" in seen["url"] and "to=200" in seen["url"] and "count=100" in seen["url"]


def test_create_payment_link_sends_notes_only_when_given(keys):
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "plink_1", "status": "created", "short_url": "u"})

    client = RazorpayClient(transport=httpx.MockTransport(handler))
    client.create_payment_link(19900, "d", "ref-1")
    client.create_payment_link(19900, "d", "ref-2", notes={"customer_id": "cust_0001"})
    assert "notes" not in bodies[0]
    assert bodies[1]["notes"] == {"customer_id": "cust_0001"}
    assert bodies[1]["amount"] == 19900 and isinstance(bodies[1]["amount"], int)
