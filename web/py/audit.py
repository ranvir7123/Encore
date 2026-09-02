import json
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


class AttemptLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        if path.exists():
            self._seen = set(path.read_text(encoding="utf-8").split())

    def already_executed(self, aid: str) -> bool:
        return aid in self._seen

    def record(self, aid: str) -> None:
        self._seen.add(aid)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(aid + "\n")
