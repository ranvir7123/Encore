from encore.report import format_rupees, render

# Fixture mirrors the real runs/eval.json shape (Task 12 brief): keys are
# "{regime}/{policy}", values carry the four eval-matrix metrics plus
# denials_by_reason and compliance_violations. Numbers below are lifted
# straight from the real r1_shifted/encore_learned and r1_shifted/fixed_t123
# cells so the rupee-formatting assertion is checking a real figure, not an
# invented one.
FIXTURE_EVAL = {
    "r1_shifted/fixed_t123": {
        "recovered_per_1000_failures_paise": 5277463,
        "recovery_per_attempt_paise": 3101,
        "max_contacts_per_customer": 3,
        "parked_paise": 16823500,
        "denials_by_reason": {"sequence_killed": 97, "hard_decline_terminal": 185},
        "compliance_violations": 0,
    },
    "r1_shifted/encore_learned": {
        "recovered_per_1000_failures_paise": 15029150,
        "recovery_per_attempt_paise": 10467,
        "max_contacts_per_customer": 3,
        "parked_paise": 9597500,
        "denials_by_reason": {"sequence_killed": 97, "hard_decline_terminal": 185},
        "compliance_violations": 0,
    },
}


def test_format_rupees_indian_grouping():
    # Indian digit grouping chosen (not western thousands-grouping) because
    # this is an INR/Razorpay product -- lakhs/crores is the reader's native
    # convention. 15029150 paise == Rs 150291.50 == "1,50,291" grouped
    # Indian-style (last 3 digits, then pairs), plus 2dp paise-derived cents.
    assert format_rupees(15029150) == "₹1,50,291.50"


def test_format_rupees_small_amount_no_grouping_needed():
    assert format_rupees(12345) == "₹123.45"


def test_render_contains_violations_row():
    html = render(FIXTURE_EVAL)
    assert "Violations: 0" in html


def test_render_contains_a_correctly_formatted_rupee_figure():
    html = render(FIXTURE_EVAL)
    # recovered_per_1000_failures_paise for r1_shifted/encore_learned, 15029150 paise.
    assert "₹1,50,291.50" in html


def test_render_contains_denial_reason_breakdown():
    html = render(FIXTURE_EVAL)
    assert "sequence_killed" in html
    assert "hard_decline_terminal" in html


def test_render_contains_parked_revenue_line():
    html = render(FIXTURE_EVAL)
    # total parked_paise across the fixture's two cells: 16823500 + 9597500 = 26421000
    assert format_rupees(16823500 + 9597500) in html


def test_render_never_crashes_without_audit_sample():
    html = render(FIXTURE_EVAL)
    # The section heading always contains "audit", so that alone proves
    # nothing -- assert the actual missing-audit placeholder marker
    # (report.py::_audit_trail_section's audit_sample=None branch).
    assert 'id="audit-trail-missing"' in html


def test_render_includes_audit_sample_when_given():
    audit_sample = ("cust_0030", [
        {"event": "decision", "customer_id": "cust_0030", "attempt_id": "cust_0030:eval_s100:retry:1",
         "kind": "retry", "at_hour": 146, "allowed": True, "reason": "ok", "policy": "encore_learned"},
        {"event": "execution", "customer_id": "cust_0030", "attempt_id": "cust_0030:eval_s100:retry:1",
         "at_hour": 146, "outcome": "success", "amount_paise": 99900, "policy": "encore_learned",
         "original_decline": "insufficient_funds", "attempt_no": 1},
    ])
    html = render(FIXTURE_EVAL, audit_sample=audit_sample)
    assert "cust_0030" in html
    assert "insufficient_funds" in html
