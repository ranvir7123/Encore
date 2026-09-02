"""Tests for the pure transforms behind the static evidence site.

webdata is deliberately I/O-free (cli.cmd_web does the reading and writing),
so everything here runs against fixture dicts rather than a real eval. What
needs pinning is not "does it produce JSON" but "can the site silently go
stale or misreport" -- a missing cell, a policy renamed in evaluate.py but
not here, or a day bucket that quietly drops retries.
"""
import pytest

from encore.evaluate import EVAL_HORIZON_HOURS
from encore.webdata import (
    POLICY_ORDER,
    REGIME_ORDER,
    build_cliff,
    build_results,
)

PROV = {"seeds": [100, 101, 102], "customers": 500}


def _cell(recovered: int = 100_000, per_attempt: int = 200, violations: int = 0) -> dict:
    return {
        "recovered_per_1000_failures_paise": recovered,
        "recovery_per_attempt_paise": per_attempt,
        "max_contacts_per_customer": 3,
        "parked_paise": 0,
        "denials_by_reason": {"cooldown_active": 4},
        "compliance_violations": violations,
    }


def _full_eval(**overrides) -> dict:
    ev = {f"{r}/{p}": _cell() for r in REGIME_ORDER for p in POLICY_ORDER}
    ev.update(overrides)
    return ev


# --- build_results -----------------------------------------------------------

def test_results_carry_every_regime_policy_cell():
    out = build_results(_full_eval(), **PROV)
    assert len(out["cells"]) == len(REGIME_ORDER) * len(POLICY_ORDER) == 18
    for regime in REGIME_ORDER:
        for policy in POLICY_ORDER:
            assert f"{regime}/{policy}" in out["cells"]


def test_missing_cell_is_rejected_rather_than_rendered_half_built():
    """A truncated eval must fail the build, not deploy a page with holes."""
    broken = _full_eval()
    del broken["r1_shifted/random_in_horizon"]
    with pytest.raises(ValueError, match="r1_shifted/random_in_horizon"):
        build_results(broken, **PROV)


def test_unknown_cell_is_rejected_so_a_renamed_policy_cannot_desync_the_site():
    extra = _full_eval()
    extra["r1_shifted/some_new_policy"] = _cell()
    with pytest.raises(ValueError, match="some_new_policy"):
        build_results(extra, **PROV)


def test_policy_order_matches_the_matrix_evaluate_actually_runs():
    """If evaluate.py gains or renames a policy, this fails here rather than
    on the deployed page."""
    import random

    from encore.evaluate import RANDOM_BASELINE_SEED, REGIMES
    from encore.model import LearnedPolicy
    from encore.policies import FixedSchedule, FixedSpread10, ImmediateRetry3, RandomInHorizon

    built = [
        ImmediateRetry3().name,
        FixedSchedule().name,
        FixedSpread10().name,
        RandomInHorizon(random.Random(RANDOM_BASELINE_SEED)).name,
        LearnedPolicy(None).name,
        LearnedPolicy(None, payday_flag=False, name="encore_learned_nopayday").name,
    ]
    assert sorted(built) == sorted(POLICY_ORDER)
    assert sorted(REGIMES) == sorted(REGIME_ORDER)


def test_money_stays_integer_paise_and_formatting_is_a_separate_field():
    """CLAUDE.md: money is integer paise everywhere. The display string is
    additive, never a replacement -- a float here would be the bug."""
    out = build_results(_full_eval(), **PROV)
    cell = out["cells"]["r1_shifted/encore_learned"]
    assert isinstance(cell["recovered_per_1000_failures_paise"], int)
    assert isinstance(cell["recovery_per_attempt_paise"], int)
    assert cell["recovered_per_1000_display"].startswith("₹")


def test_totals_report_violations_across_every_cell():
    ev = _full_eval(**{"r2_no_signal/fixed_t123": _cell(violations=2)})
    out = build_results(ev, **PROV)
    assert out["totals"]["cells"] == 18
    assert out["totals"]["compliance_violations"] == 2


def test_ratio_against_the_industry_baseline_is_reported_per_regime():
    ev = _full_eval(**{
        "r1_shifted/fixed_t123": _cell(recovered=50_000),
        "r1_shifted/encore_learned": _cell(recovered=150_000),
        "r1_shifted/random_in_horizon": _cell(recovered=200_000),
    })
    out = build_results(ev, **PROV)
    head = out["headline"]["r1_shifted"]
    assert head["learned_over_fixed_t123"] == pytest.approx(3.0)
    assert head["random_over_learned"] == pytest.approx(200_000 / 150_000)


def test_zero_baseline_does_not_divide_by_zero():
    """immediate_x3 recovers exactly 0 in every regime -- a ratio against it
    must be None, not a crash and not infinity."""
    ev = _full_eval(**{"r0_base/immediate_x3": _cell(recovered=0)})
    out = build_results(ev, **PROV)
    assert out["cells"]["r0_base/immediate_x3"]["over_fixed_t123"] is not None
    ev2 = _full_eval(**{"r0_base/fixed_t123": _cell(recovered=0)})
    out2 = build_results(ev2, **PROV)
    assert out2["headline"]["r0_base"]["learned_over_fixed_t123"] is None


def test_provenance_names_the_seeds_customers_and_exact_command():
    out = build_results(_full_eval(), **PROV)
    prov = out["provenance"]
    assert prov["seeds"] == [100, 101, 102]
    assert prov["customers"] == 500
    assert "encore eval" in prov["command"]
    assert "100,101,102" in prov["command"]


# --- build_cliff -------------------------------------------------------------

def _ex(at_hour: int, success: bool) -> dict:
    return {"event": "execution", "at_hour": at_hour,
            "outcome": "success" if success else "failure"}


def test_cliff_buckets_executions_by_day_of_month():
    execs = {
        "encore_learned": [_ex(20 * 24 + 23, False), _ex(20 * 24 + 2, True),
                           _ex(24 * 24 + 23, True)],
        "random_in_horizon": [_ex(24 * 24 + 23, True)],
    }
    out = build_cliff(execs, regime="r1_shifted", **PROV)
    learned = out["series"]["encore_learned"]
    # hour 20*24+23 and 20*24+2 are both day-of-month 21
    assert learned["tried"][out["days"].index(21)] == 2
    assert learned["won"][out["days"].index(21)] == 1
    assert learned["tried"][out["days"].index(25)] == 1
    assert learned["won"][out["days"].index(25)] == 1


def test_cliff_covers_every_day_in_the_evaluated_window_even_empty_ones():
    """A day with no retries must render as a zero bar, not vanish and shift
    the axis under the neighbouring days."""
    out = build_cliff({"encore_learned": [_ex(24 * 24 + 23, True)]},
                      regime="r1_shifted", **PROV)
    assert out["days"] == list(range(1, EVAL_HORIZON_HOURS // 24 + 1))
    assert len(out["series"]["encore_learned"]["tried"]) == len(out["days"])
    assert sum(out["series"]["encore_learned"]["tried"]) == 1


def test_cliff_ignores_non_execution_events():
    execs = {"encore_learned": [
        _ex(24 * 24 + 23, True),
        {"event": "decision", "at_hour": 3 * 24, "allowed": False, "reason": "cooldown_active"},
        {"event": "park", "customer_id": "cust_0001"},
    ]}
    out = build_cliff(execs, regime="r1_shifted", **PROV)
    assert sum(out["series"]["encore_learned"]["tried"]) == 1


def test_cliff_reports_win_rate_per_day_and_leaves_untried_days_null():
    """The success-rate overlay is the step function itself. A day nobody
    tried has no measured rate -- it must be null, not 0%, or the chart
    invents a cliff where there is only missing data."""
    execs = {"encore_learned": [_ex(24 * 24 + 23, True), _ex(24 * 24 + 1, False)]}
    out = build_cliff(execs, regime="r1_shifted", **PROV)
    rates = out["series"]["encore_learned"]["win_rate"]
    assert rates[out["days"].index(25)] == pytest.approx(0.5)
    assert rates[out["days"].index(4)] is None


def test_cliff_rejects_an_execution_past_the_evaluated_window():
    """BROKELOG 2026-09-02: those were free wins. If one reappears in the
    audit logs, the chart must refuse to render it rather than draw it."""
    with pytest.raises(ValueError, match="past the evaluated window"):
        build_cliff({"encore_learned": [_ex(EVAL_HORIZON_HOURS + 5, True)]},
                    regime="r1_shifted", **PROV)


def test_cliff_totals_match_the_series():
    execs = {"encore_learned": [_ex(24 * 24 + 23, True), _ex(20 * 24 + 23, False)]}
    out = build_cliff(execs, regime="r1_shifted", **PROV)
    series = out["series"]["encore_learned"]
    assert series["total_tried"] == sum(series["tried"]) == 2
    assert series["total_won"] == sum(series["won"]) == 1
