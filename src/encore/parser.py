import json
import os
import re
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


SYSTEM = """You classify a subscription customer's reply about a failed payment.
Return ONLY JSON: {"kind": "promise_to_pay"|"cancel"|"dispute"|"other",
"promise_day": <int 1-30 or null>}. promise_day is the day of month they say
money arrives. Replies may be Hindi/Hinglish. Do not invent a day."""


def parse_llm(text: str, model: str = "claude-sonnet-5") -> ReplyIntent:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=model, max_tokens=100, system=SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    try:
        return ReplyIntent(**json.loads(msg.content[0].text))
    except Exception:  # noqa: BLE001 -- intentional: any validation failure must fall back, never break the pipeline
        return parse_keyword(text)  # the model never gets to break the pipeline
