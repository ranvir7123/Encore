import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

CANCEL_WORDS = re.compile(r"\b(cancel|band|stop|unsubscribe|nahi chahiye)\b", re.IGNORECASE)
PROMISE_DAY = re.compile(r"\b(\d{1,2})\s*(tarikh|th|st|nd|rd)\b", re.IGNORECASE)
PROMISE_WORDS = re.compile(r"\b(salary|pay|paisa|baad|after|next week|retry)\b", re.IGNORECASE)


class ReplyIntent(BaseModel):
    kind: Literal["promise_to_pay", "cancel", "dispute", "other"]
    promise_day: int | None = Field(default=None, ge=1, le=30)


def parse_keyword(text: str) -> ReplyIntent:
    if CANCEL_WORDS.search(text):
        return ReplyIntent(kind="cancel")
    day_match = PROMISE_DAY.search(text)
    if day_match and 1 <= int(day_match.group(1)) <= 30:
        return ReplyIntent(kind="promise_to_pay", promise_day=int(day_match.group(1)))
    if PROMISE_WORDS.search(text):
        return ReplyIntent(kind="promise_to_pay")
    return ReplyIntent(kind="other")


def evaluate(parser_fn: Callable[[str], ReplyIntent], eval_path: Path) -> dict:
    """Score parser_fn against a labeled JSONL set of {text, kind, promise_day} rows.

    correct_kind counts rows where the predicted kind matches the label.
    correct_full additionally requires promise_day to match exactly.
    """
    rows = [
        json.loads(line)
        for line in Path(eval_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    n = len(rows)
    correct_kind = 0
    correct_full = 0
    for row in rows:
        gold = ReplyIntent(kind=row["kind"], promise_day=row["promise_day"])
        pred = parser_fn(row["text"])
        if pred.kind == gold.kind:
            correct_kind += 1
            if pred.promise_day == gold.promise_day:
                correct_full += 1
    return {
        "n": n,
        "correct_kind": correct_kind,
        "correct_full": correct_full,
        "accuracy_kind": correct_kind / n if n else 0.0,
        "accuracy_full": correct_full / n if n else 0.0,
    }


SYSTEM = """You classify a subscription customer's reply about a failed payment.
Return ONLY JSON: {"kind": "promise_to_pay"|"cancel"|"dispute"|"other",
"promise_day": <int 1-30 or null>}. promise_day is the day of month they say
money arrives. Replies may be Hindi/Hinglish. Do not invent a day."""


def parse_llm(text: str, model: str = "claude-sonnet-5") -> ReplyIntent:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(
            model=model, max_tokens=100, system=SYSTEM,
            messages=[{"role": "user", "content": text}],
        )
        return ReplyIntent(**json.loads(msg.content[0].text))
    except Exception:  # noqa: BLE001 -- intentional: any failure (missing key, network, API error, JSON, validation) must fall back, never break the pipeline
        return parse_keyword(text)  # the model never gets to break the pipeline
