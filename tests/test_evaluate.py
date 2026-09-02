import glob
import json
from pathlib import Path

from encore.evaluate import (
    EVAL_HORIZON_HOURS,
    REGIMES,
    count_violations,
    run_matrix,
)


def test_regimes_are_distinct():
    assert REGIMES["r1_shifted"].salary_days != REGIMES["r0_base"].salary_days
    assert REGIMES["r2_no_signal"].uniform_credits


def test_matrix_runs_and_no_policy_violates_the_wall(tmp_path: Path):
    results = run_matrix(seeds=[100], out_dir=tmp_path, n_customers=150)
    for cell, metrics in results.items():
        assert metrics["compliance_violations"] == 0, f"{cell} violated the wall"
    assert results["r1_shifted/encore_learned"]["recovered_per_1000_failures_paise"] >= 0


def test_rerun_into_same_out_dir_does_not_corrupt_results(tmp_path: Path):
    # BROKELOG-worthy bug: per-cell AttemptLedger/AuditLog files used to persist
    # across runs, so a second run_matrix() into the same out_dir saw every
    # attempt_id as already-executed (duplicate_blocked everywhere) and wrote
    # near-zero recovery with no warning. run_matrix must wipe each cell's
    # audit/ledger files before it writes to them, so two runs into the same
    # out_dir produce identical results.
    first = run_matrix(seeds=[100], out_dir=tmp_path, n_customers=60)
    second = run_matrix(seeds=[100], out_dir=tmp_path, n_customers=60)
    assert second == first
    # r1_shifted/encore_learned recovers something nonzero even in this tiny
    # world -- pin equality on a real, nonzero number, not just 0 == 0.
    recovered = first["r1_shifted/encore_learned"]["recovered_per_1000_failures_paise"]
    assert recovered > 0
    assert second["r1_shifted/encore_learned"]["recovered_per_1000_failures_paise"] == recovered


def test_violation_checker_actually_catches_violations(tmp_path: Path):
    # A forged audit log with an execution on a hard-declined, revoked customer
    from encore.audit import AuditLog
    log = AuditLog(tmp_path / "forged.jsonl")
    log.append({"event": "execution", "customer_id": "c1", "attempt_id": "c1:x:retry:5",
                "at_hour": 12, "outcome": "failure", "amount_paise": 100,
                "original_decline": "mandate_revoked", "attempt_no": 5})
    assert count_violations(log.read_all()) > 0


def test_no_policy_executes_past_the_simulated_horizon(tmp_path: Path):
    """BROKELOG 2026-09-02. run_matrix simulates exactly 30 days, so a retry at
    day >= 30 has no balance_history entry and Portfolio.debit falls back to the
    live end-of-simulation balance -- a free success no policy earned. Before
    the clamp, random_in_horizon scored 52 such wins on r1_shifted at a 100%
    success rate while encore_learned scored none, which alone was 14% of the
    control's published margin. This asserts on the audit log rather than on
    the policies, so it still fails if a future policy bypasses
    legal_candidate_hours entirely.
    """
    run_matrix(seeds=[100], out_dir=tmp_path, n_customers=150)
    offenders = []
    for path in sorted(glob.glob(str(tmp_path / "*_audit.jsonl"))):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if (record.get("event") == "execution"
                        and record["at_hour"] >= EVAL_HORIZON_HOURS):
                    offenders.append((Path(path).name, record["at_hour"]))
    assert not offenders, (
        f"{len(offenders)} execution(s) past hour {EVAL_HORIZON_HOURS} "
        f"(day {EVAL_HORIZON_HOURS // 24}): {offenders[:5]}"
    )


def test_matrix_has_32_cells_and_both_promise_policies_are_present(tmp_path: Path):
    results = run_matrix(seeds=[100], out_dir=tmp_path, n_customers=60)
    assert len(results) == 32
    assert "r3_noisy_promise/promise_aware" in results
    assert "r3_noisy_promise/promise_aware_random" in results
    assert all(cell["compliance_violations"] == 0 for cell in results.values())


def test_promises_reach_the_policy_from_parsed_replies(tmp_path: Path, monkeypatch):
    from encore.policies import PromiseAwarePolicy

    seen: dict = {}
    real = PromiseAwarePolicy.propose

    def spy(self, failed, state, now_hour):
        seen.setdefault("promises", dict(self.promises))
        return real(self, failed, state, now_hour)

    monkeypatch.setattr(PromiseAwarePolicy, "propose", spy)
    run_matrix(seeds=[100], out_dir=tmp_path, n_customers=200)
    assert seen["promises"] and all(1 <= d <= 30 for d in seen["promises"].values())
