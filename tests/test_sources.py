"""Failure sources: the simulated cycle and real Razorpay failed payments
must yield the same FailedDebit shape, and anything we cannot classify must
surface as an exception rather than a guessed retry."""
from encore.domain import DeclineCode
from encore.simulator import Portfolio, RegimeConfig
from encore.sources import (
    IST_OFFSET_S,
    RazorpayFailureSource,
    SimulatedFailureSource,
    map_error_reason,
    sim_hour,
)

R0 = RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05)
ANCHOR = 1788287400  # 2026-09-01 00:00 IST (18:30 UTC on 2026-08-31)


class FakeClient:
    def __init__(self, items):
        self.items = items

    def list_payments(self, from_ts, to_ts, count=100, skip=0):
        return self.items


def _payment(**over):
    base = {"id": "pay_1", "status": "failed", "amount": 19900, "created_at": ANCHOR + 14 * 3600,
            "error_reason": "insufficient_funds", "notes": {"customer_id": "cust_0042"}}
    base.update(over)
    return base


def test_mapping_is_explicit_and_unknown_is_none():
    assert map_error_reason("insufficient_funds") is DeclineCode.INSUFFICIENT_FUNDS
    assert map_error_reason("gateway_technical_error") is DeclineCode.GATEWAY_TIMEOUT
    assert map_error_reason("card_declined") is None
    assert map_error_reason(None) is None


def test_sim_hour_keeps_ist_hour_of_day_and_counts_days_from_anchor():
    assert sim_hour(ANCHOR, ANCHOR) == 0
    assert sim_hour(ANCHOR + 14 * 3600, ANCHOR) == 14
    assert sim_hour(ANCHOR + 2 * 86400 + 23 * 3600, ANCHOR) == 2 * 24 + 23
    assert IST_OFFSET_S == 19800


def test_razorpay_source_yields_failed_debits_with_customer_from_notes():
    src = RazorpayFailureSource(FakeClient([_payment()]), ANCHOR, ANCHOR + 86400, "live", ANCHOR)
    [f] = src.failures()
    assert f.customer_id == "cust_0042" and f.amount_paise == 19900
    assert f.decline is DeclineCode.INSUFFICIENT_FUNDS and f.at_hour == 14 and f.cycle_id == "live"
    assert src.unmapped == []


def test_razorpay_source_skips_non_failed_and_parks_unmapped():
    items = [_payment(status="captured"), _payment(id="pay_2", error_reason="card_declined"),
             _payment(id="pay_3", notes={})]
    src = RazorpayFailureSource(FakeClient(items), ANCHOR, ANCHOR + 86400, "live", ANCHOR)
    fails = src.failures()
    assert [f.customer_id for f in fails] == ["rzp:pay_3"]
    assert src.unmapped == [{"payment_id": "pay_2", "customer_id": "cust_0042",
                             "error_reason": "card_declined", "amount_paise": 19900}]


def test_simulated_source_equals_run_cycle():
    a = Portfolio.generate(100, R0, seed=7)
    b = Portfolio.generate(100, R0, seed=7)
    assert SimulatedFailureSource(a, "c1").failures() == b.run_cycle(30, "c1")
