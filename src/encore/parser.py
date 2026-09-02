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


def anthropic_headers() -> dict[str, str]:
    """Identity-linked API keys must name the workspace every request acts in
    (`anthropic-workspace-id`); plain keys need nothing. Read from
    ANTHROPIC_WORKSPACE_ID so the key type stays a deployment detail."""
    workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    return {"anthropic-workspace-id": workspace} if workspace else {}


def parse_llm(text: str, model: str = "claude-sonnet-5", strict: bool = False) -> ReplyIntent:
    """Classify one reply with a Claude model, through the same pydantic
    ReplyIntent the keyword parser uses.

    On the money-adjacent path (strict=False, the default) ANY failure --
    missing key, network, API error, bad JSON, validation -- falls back to
    parse_keyword, so the model can never break the pipeline. `encore
    parse-eval` passes strict=True: a measurement must not quietly turn into
    the keyword parser's numbers wearing a model's name."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"],
                                     default_headers=anthropic_headers())
        msg = client.messages.create(
            model=model, max_tokens=400, system=SYSTEM,
            messages=[{"role": "user", "content": text}],
        )
        # models with thinking on return a thinking block first; take the text one
        reply = next(b.text for b in msg.content if b.type == "text")
        return ReplyIntent(**json.loads(reply))
    except Exception:
        if strict:
            raise
        return parse_keyword(text)  # the model never gets to break the pipeline
