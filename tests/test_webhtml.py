"""Tests for the static renderers behind the evidence site.

The cliff chart is Tier B: it must be complete before any JavaScript runs, so
what is pinned here is that the SVG actually carries the numbers (not that it
looks nice), that every value is escaped, and that the accessible table says
the same thing the picture does.
"""
import re

import pytest

from encore.webdata import build_cliff, build_results
from encore.webhtml import (
    render_cliff_svg,
    render_cliff_table,
    render_headline_figures,
    render_provenance,
)
from tests.test_webdata import PROV, _ex, _full_eval


def _cliff(**series) -> dict:
    return build_cliff(series or {"encore_learned": [], "random_in_horizon": []},
                       regime="r1_shifted", **PROV)


def test_svg_draws_one_bar_per_nonzero_day_and_none_for_empty_days():
    cliff = _cliff(
        encore_learned=[_ex(20 * 24 + 23, False), _ex(24 * 24 + 23, True)],
        random_in_horizon=[_ex(24 * 24 + 23, True)],
    )
    svg = render_cliff_svg(cliff)
    # 2 learned bars (days 21, 25) + 1 control bar (day 25) = 3
    assert len(re.findall(r'<rect class="bar-', svg)) == 3


def test_svg_is_static_and_carries_the_counts_without_javascript():
    """No <script>, and the numbers are in the markup rather than fetched."""
    cliff = _cliff(encore_learned=[_ex(24 * 24 + 23, True), _ex(24 * 24 + 1, False)])
    svg = render_cliff_svg(cliff)
    assert "<script" not in svg.lower()
    assert 'data-day="25"' in svg
    assert 'data-tried="2"' in svg
    assert 'data-won="1"' in svg


def test_svg_is_labelled_for_screen_readers():
    svg = render_cliff_svg(_cliff(encore_learned=[_ex(24 * 24 + 23, True)]))
    assert 'role="img"' in svg
    assert 'aria-labelledby="cliff-title cliff-desc"' in svg
    assert "<title id=\"cliff-title\">" in svg
    assert "<desc id=\"cliff-desc\">" in svg


def test_svg_marks_the_cliff_day_it_was_given_not_a_hardcoded_one():
    cliff = _cliff(encore_learned=[_ex(24 * 24 + 23, True)])
    assert "day 25: success jumps to 100%" in render_cliff_svg(cliff)
    assert "day 12: success jumps to 100%" in render_cliff_svg(cliff, cliff_day=12)


def test_svg_scales_to_the_taller_series_so_both_share_one_axis():
    """A per-series axis would hide the concentration the chart exists to show."""
    tall = _cliff(
        encore_learned=[_ex(22 * 24 + 23, False)] * 200,
        random_in_horizon=[_ex(22 * 24 + 23, False)] * 10,
    )
    svg = render_cliff_svg(tall)
    heights = [float(h) for h in re.findall(r'<rect class="bar-\w+"[^>]*height="([\d.]+)"', svg)]
    assert len(heights) == 2
    # 200 vs 10 on a shared axis is a 20x height difference, within rounding
    assert heights[0] / heights[1] == pytest.approx(20, rel=0.02)


def test_empty_cliff_still_renders_a_scale_rather_than_dividing_by_zero():
    svg = render_cliff_svg(_cliff())
    assert "<svg" in svg
    assert '<rect class="bar-' not in svg


def test_table_lists_every_day_and_marks_untried_days_as_having_no_rate():
    cliff = _cliff(encore_learned=[_ex(24 * 24 + 23, True)])
    table = render_cliff_table(cliff)
    assert len(re.findall(r"<tr><td>\d+</td>", table)) == 30
    assert "no retries" in table  # days nobody tried
    assert "100%" in table  # day 25


def test_table_and_svg_report_the_same_totals():
    cliff = _cliff(
        encore_learned=[_ex(24 * 24 + 23, True), _ex(20 * 24 + 23, False)],
        random_in_horizon=[_ex(26 * 24 + 23, True)],
    )
    svg, table = render_cliff_svg(cliff), render_cliff_table(cliff)
    assert 'data-tried="1"' in svg
    # day 21 row: model tried 1, won 0; control tried 0
    assert "<tr><td>21</td><td>1</td><td>0</td><td>0</td><td>0</td>" in table


def test_provenance_states_seeds_customers_and_the_command():
    out = render_provenance(_cliff()["provenance"])
    assert "100, 101, 102" in out
    assert "500" in out
    assert "encore eval --seeds 100,101,102 --customers 500" in out


def test_headline_figures_come_from_the_generated_data_not_a_literal():
    results = build_results(_full_eval(**{
        "r1_shifted/fixed_t123": {**_blank(), "recovered_per_1000_failures_paise": 50_000},
        "r1_shifted/encore_learned": {**_blank(), "recovered_per_1000_failures_paise": 150_000},
        "r1_shifted/random_in_horizon": {**_blank(), "recovered_per_1000_failures_paise": 225_000},
    }), **PROV)
    out = render_headline_figures(results, _cliff(), test_count=104)
    assert "3.00x" in out          # 150000 / 50000
    assert "+50%" in out           # 225000 / 150000
    assert "104" in out
    assert ">0<" in out            # zero violations


def test_renderers_escape_values_that_trace_back_to_the_audit_log():
    cliff = _cliff()
    cliff["series"]["<img src=x onerror=alert(1)>"] = {
        "tried": [0] * 30, "won": [0] * 30, "win_rate": [None] * 30,
        "total_tried": 0, "total_won": 0,
    }
    cliff["regime"] = "<script>alert(1)</script>"
    svg = render_cliff_svg(cliff)
    assert "<script>alert(1)</script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "<script>alert(1)</script>" not in render_cliff_table(cliff)


def _blank() -> dict:
    return {
        "recovered_per_1000_failures_paise": 100_000,
        "recovery_per_attempt_paise": 200,
        "max_contacts_per_customer": 3,
        "parked_paise": 0,
        "denials_by_reason": {},
        "compliance_violations": 0,
    }


def test_hero_test_count_default_matches_the_actual_suite_size():
    """The hero states "N tests passing". That number is a CLI default, which
    is exactly the kind of figure that goes stale silently once someone adds a
    test -- so the suite counts itself and fails here instead of letting the
    deployed page overstate or understate the evidence.

    Collection runs in a subprocess because pytest is not re-entrant.
    """
    import subprocess
    import sys

    from encore.cli import build_parser

    default = build_parser().parse_args(["web"]).test_count
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, check=True,
    )
    match = re.search(r"(\d+) tests? collected", proc.stdout)
    assert match, f"could not read a collection count from:\n{proc.stdout[-500:]}"
    collected = int(match.group(1))
    assert default == collected, (
        f"`encore web --test-count` defaults to {default} but the suite now has "
        f"{collected} tests. Update the default in cli.py so the hero stays honest."
    )
