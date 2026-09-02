"""The live board is a pure transform over the agent's audit records plus an
f-string page. These fixtures cover every event kind the agent writes."""
from pathlib import Path

from encore.board import build_board, render_board, write_board

RECORDS = [
    {"event": "nudge", "customer_id": "c1", "attempt_id": "c1:x:nudge:1", "at_hour": 10},
    {"event": "reply", "customer_id": "c1", "at_hour": 12, "text": "salary 25 tarikh",
     "kind": "promise_to_pay", "promise_day": 25},
    {"event": "decision", "customer_id": "c1", "attempt_id": "c1:x:retry:1", "kind": "retry",
     "at_hour": 599, "allowed": True, "reason": "ok", "policy": "promise_aware"},
    {"event": "link_created", "customer_id": "c1", "attempt_id": "c1:x:retry:1", "at_hour": 599,
     "amount_paise": 19900, "rail": "razorpay_test_mode", "link_id": "plink_1",
     "short_url": "https://rzp.io/1", "status": "created"},
    {"event": "decision", "customer_id": "c2", "attempt_id": "c2:x:retry:1", "kind": "retry",
     "at_hour": 30, "allowed": False, "reason": "hard_decline_terminal", "policy": "promise_aware"},
    {"event": "park", "customer_id": "c2", "reason": "hard_decline_terminal",
     "policy": "promise_aware", "amount_paise": 49900},
    {"event": "execution", "customer_id": "c3", "attempt_id": "c3:x:retry:1", "at_hour": 95,
     "outcome": "success", "amount_paise": 29900, "policy": "promise_aware",
     "original_decline": "insufficient_funds", "attempt_no": 1, "rail": "simulated"},
    {"event": "park", "customer_id": "rzp:pay_9", "reason": "unmapped_error_reason",
     "error_reason": "card_declined", "payment_id": "pay_9", "amount_paise": 9900,
     "policy": "promise_aware"},
]
AT_RISK = {"c1": 19900, "c2": 49900, "c3": 29900, "rzp:pay_9": 9900}


def test_build_board_totals_and_exceptions():
    b = build_board(RECORDS, AT_RISK)
    assert b["at_risk_paise"] == 109600 and b["recovered_paise"] == 29900
    assert b["in_flight"] == 1 and b["attempts"] == 1 and b["nudges"] == 1 and b["replies"] == 1
    assert b["denials"] == {"hard_decline_terminal": 1}
    assert b["parked"] == {"hard_decline_terminal": 1, "unmapped_error_reason": 1}
    rows = {c["customer_id"]: c for c in b["customers"]}
    assert rows["c1"]["link_id"] == "plink_1" and rows["c1"]["last_event"] == "link_created"
    assert rows["c1"]["rail"] == "razorpay_test_mode"
    assert rows["c3"]["last_event"] == "recovered"
    assert rows["c2"]["last_event"] == "parked: hard_decline_terminal"
    assert rows["rzp:pay_9"]["last_event"] == "parked: unmapped_error_reason"
    assert b["customers"][0]["customer_id"] == "c1"  # live-rail rows sort first


def test_render_board_is_html_with_rupees_and_refresh(tmp_path: Path):
    html = render_board(build_board(RECORDS, AT_RISK), "seed 100, r1_shifted")
    assert "₹299.00" in html and "₹1,096.00" in html and 'http-equiv="refresh"' in html
    assert "plink_1" in html and "hard_decline_terminal" in html and "seed 100" in html
    assert "<script" not in html
    write_board(tmp_path / "board.html", build_board(RECORDS, AT_RISK), "p")
    text = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>") and not (tmp_path / "board.html.tmp").exists()
