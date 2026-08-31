from pathlib import Path

from encore.parser import ReplyIntent, evaluate, parse_keyword, parse_llm


def test_cancel_hinglish():
    assert parse_keyword("band kar do isko").kind == "cancel"
    assert parse_keyword("cancel karo yeh subscription").kind == "cancel"


def test_promise_with_tarikh_date():
    intent = parse_keyword("salary 5 tarikh ko aayegi, tab try karna")
    assert intent.kind == "promise_to_pay"
    assert intent.promise_day == 5


def test_unknown_text_is_other_never_a_guess():
    assert parse_keyword("kya haal hai bhai").kind == "other"


def test_intent_schema_rejects_out_of_range_day():
    import pytest
    with pytest.raises(ValueError):
        ReplyIntent(kind="promise_to_pay", promise_day=42)


def test_evaluate_keyword_parser_on_labeled_set():
    result = evaluate(parse_keyword, Path("data/reply_eval.jsonl"))
    assert result["n"] == 40
    # Deterministic: measured directly against the current keyword-parser regexes
    # and the current data/reply_eval.jsonl labels. If either changes, re-measure
    # before updating these numbers.
    assert result["correct_kind"] == 27
    assert result["correct_full"] == 27
    assert result["accuracy_kind"] == 27 / 40
    assert result["accuracy_full"] == 27 / 40


def test_parse_llm_falls_back_when_api_key_missing(monkeypatch):
    # No network call happens: the missing key raises KeyError before any
    # request is made, and that failure must be caught, not propagated.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert parse_llm("band kar do isko").kind == "cancel"
