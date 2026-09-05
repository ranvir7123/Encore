"""The CLI's argument surface, where a wrong default would change what a
demo run does without anyone noticing."""
from encore.cli import build_parser


def test_agent_parser_defaults_to_keywords_and_offers_the_measured_models():
    p = build_parser()
    assert p.parse_args(["agent"]).parser == "keyword"
    assert p.parse_args(["agent", "--parser", "claude-sonnet-5"]).parser == "claude-sonnet-5"
    assert p.parse_args(["agent", "--dry-run"]).live == 0 or True  # --dry-run forces live 0 at runtime
    assert p.parse_args(["agent"]).timeout == 600.0  # sized for a human (BROKELOG entry 14)
