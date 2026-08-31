from pathlib import Path

from encore.audit import AttemptLedger, AuditLog


def test_audit_log_appends_and_reads_back(tmp_path: Path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append({"event": "decision", "reason": "ok"})
    log.append({"event": "execution", "outcome": "success"})
    assert [r["event"] for r in log.read_all()] == ["decision", "execution"]


def test_ledger_blocks_duplicate_execution(tmp_path: Path):
    led = AttemptLedger(tmp_path / "ledger.txt")
    assert not led.already_executed("c1:2026-09:retry:1")
    led.record("c1:2026-09:retry:1")
    assert led.already_executed("c1:2026-09:retry:1")


def test_ledger_survives_crash_restart(tmp_path: Path):
    p = tmp_path / "ledger.txt"
    AttemptLedger(p).record("c1:2026-09:retry:1")
    fresh = AttemptLedger(p)  # simulates process restart
    assert fresh.already_executed("c1:2026-09:retry:1")
