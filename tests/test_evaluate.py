from pathlib import Path

from encore.evaluate import REGIMES, count_violations, run_matrix


def test_regimes_are_distinct():
    assert REGIMES["r1_shifted"].salary_days != REGIMES["r0_base"].salary_days
    assert REGIMES["r2_no_signal"].uniform_credits


def test_matrix_runs_and_no_policy_violates_the_wall(tmp_path: Path):
    results = run_matrix(seeds=[100], out_dir=tmp_path, n_customers=150)
    for cell, metrics in results.items():
        assert metrics["compliance_violations"] == 0, f"{cell} violated the wall"
    assert results["r1_shifted/encore_learned"]["recovered_per_1000_failures_paise"] >= 0


def test_violation_checker_actually_catches_violations(tmp_path: Path):
    # A forged audit log with an execution on a hard-declined, revoked customer
    from encore.audit import AuditLog
    log = AuditLog(tmp_path / "forged.jsonl")
    log.append({"event": "execution", "customer_id": "c1", "attempt_id": "c1:x:retry:5",
                "at_hour": 12, "outcome": "failure", "amount_paise": 100,
                "original_decline": "mandate_revoked", "attempt_no": 5})
    assert count_violations(log.read_all()) > 0
