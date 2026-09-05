"""The CLI's argument surface, where a wrong default would change what a
demo run does without anyone noticing."""
from encore.cli import build_parser


def test_agent_parser_defaults_to_keywords_and_offers_the_measured_models():
    p = build_parser()
    assert p.parse_args(["agent"]).parser == "keyword"
    assert p.parse_args(["agent", "--parser", "claude-sonnet-5"]).parser == "claude-sonnet-5"
    args = p.parse_args(["agent", "--dry-run"])
    assert args.dry_run is True and args.live == 0  # cmd_agent also forces live 0 under --dry-run
    assert p.parse_args(["agent"]).timeout == 600.0  # sized for a human (BROKELOG entry 14)


def test_agent_refuses_a_parser_model_that_cannot_answer_once(monkeypatch):
    """BROKELOG entry 16 on the agent path: parse_llm falls back to keywords on
    any failure, so without a probe the board would name a model while keywords
    did the work. The probe turns that silent fallback into a refusal."""
    import pytest

    from encore import cli

    def broken(text, model, strict):
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr(cli, "parse_llm", broken)
    with pytest.raises(SystemExit, match="keyword"):
        cli._probe_parser("claude-sonnet-5")

    calls = []
    monkeypatch.setattr(cli, "parse_llm",
                        lambda text, model, strict: calls.append((model, strict)))
    cli._probe_parser("claude-sonnet-5")
    assert calls == [("claude-sonnet-5", True)]
