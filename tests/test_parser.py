from encore.parser import ReplyIntent, parse_keyword


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
