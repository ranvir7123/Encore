"""Pure transforms from `runs/` artifacts into the JSON the static site reads.

No file I/O, no clocks, no randomness: `cli.cmd_web` does all the reading and
writing, so every transform here is directly unit-testable against fixture
dicts. This mirrors how `report.render()` is already split from
`report.write_scoreboard()`, and it is why the builder lives inside the
package rather than in a loose script -- pytest covers it.

Money stays integer paise (CLAUDE.md). Where a human-readable string is
needed, it is added as a SEPARATE `*_display` field via
`report.format_rupees`; the paise integer is never replaced by a float.
"""
from encore.domain import HOURS_PER_DAY, day_of_month
from encore.evaluate import EVAL_HORIZON_HOURS
from encore.report import format_rupees

# The order the site renders, and the single place the site's idea of the
# matrix is written down. tests/test_webdata.py asserts these against the
# policies evaluate.run_matrix actually constructs and the regimes it runs,
# so renaming a policy in evaluate.py fails a test instead of silently
# desyncing the deployed page.
REGIME_ORDER = ["r0_base", "r1_shifted", "r2_no_signal", "r3_noisy_promise"]
POLICY_ORDER = [
    "immediate_x3",
    "fixed_t123",
    "fixed_spread10",
    "random_in_horizon",
    "encore_learned",
    "encore_learned_nopayday",
    "promise_aware",
]

# Tier A vs Tier B (see docs/superpowers/specs/2026-09-01-encore-web-design.md).
# The four stdlib policies can run live in the browser through Pyodide; the two
# model-backed ones cannot, because scikit-learn takes 61.7 s to install there.
LIVE_POLICIES = ["immediate_x3", "fixed_t123", "fixed_spread10", "random_in_horizon"]
# promise_aware is stdlib but needs the reply parser (pydantic), which is
# not a Tier A module in the browser -- so it is precomputed, not live.
PRECOMPUTED_POLICIES = ["encore_learned", "encore_learned_nopayday", "promise_aware"]

# The claim that survives is measured against this policy: Razorpay's
# documented T+1/T+2/T+3 subscription retry shape.
INDUSTRY_BASELINE = "fixed_t123"

RECOVERED = "recovered_per_1000_failures_paise"


def _command(seeds: list[int], customers: int) -> str:
    return f"uv run encore eval --seeds {','.join(str(s) for s in seeds)} --customers {customers}"


def _provenance(seeds: list[int], customers: int) -> dict:
    """Every generated figure carries the seeds, customer count and the exact
    command that reproduces it -- no number appears on the site without its
    origin (spec section 3)."""
    return {
        "seeds": list(seeds),
        "customers": customers,
        "command": _command(seeds, customers),
        "horizon_hours": EVAL_HORIZON_HOURS,
        "horizon_days": EVAL_HORIZON_HOURS // HOURS_PER_DAY,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    """None, never infinity: immediate_x3 recovers exactly 0 in every regime
    because the wall denies all three of its proposals, so it is a real
    denominator the site has to render."""
    if not denominator:
        return None
    return numerator / denominator


def build_results(eval_dict: dict, *, seeds: list[int], customers: int) -> dict:
    """`runs/eval.json` -> the 18-cell matrix the results table renders.

    Raises ValueError on a cell that is missing or unrecognised, so a
    truncated eval or a policy renamed in evaluate.py fails the build instead
    of deploying a page with holes in it.
    """
    expected = {f"{r}/{p}" for r in REGIME_ORDER for p in POLICY_ORDER}
    missing = sorted(expected - set(eval_dict))
    if missing:
        raise ValueError(f"eval.json is missing {len(missing)} cell(s): {', '.join(missing)}")
    unknown = sorted(set(eval_dict) - expected)
    if unknown:
        raise ValueError(
            f"eval.json has {len(unknown)} cell(s) the site does not know how to render: "
            f"{', '.join(unknown)} -- update webdata.POLICY_ORDER/REGIME_ORDER"
        )

    cells: dict[str, dict] = {}
    for regime in REGIME_ORDER:
        baseline = eval_dict[f"{regime}/{INDUSTRY_BASELINE}"][RECOVERED]
        for policy in POLICY_ORDER:
            key = f"{regime}/{policy}"
            m = eval_dict[key]
            recovered = m[RECOVERED]
            per_attempt = m["recovery_per_attempt_paise"]
            cells[key] = {
                "regime": regime,
                "policy": policy,
                "tier": "live" if policy in LIVE_POLICIES else "precomputed",
                RECOVERED: recovered,
                "recovered_per_1000_display": format_rupees(recovered),
                "recovery_per_attempt_paise": per_attempt,
                "recovery_per_attempt_display": format_rupees(per_attempt),
                "max_contacts_per_customer": m["max_contacts_per_customer"],
                "parked_paise": m["parked_paise"],
                "parked_display": format_rupees(m["parked_paise"]),
                "denials_by_reason": dict(m.get("denials_by_reason", {})),
                "compliance_violations": m["compliance_violations"],
                "over_fixed_t123": _ratio(recovered, baseline),
            }

    headline = {}
    for regime in REGIME_ORDER:
        learned = eval_dict[f"{regime}/encore_learned"][RECOVERED]
        headline[regime] = {
            "learned_over_fixed_t123": _ratio(
                learned, eval_dict[f"{regime}/{INDUSTRY_BASELINE}"][RECOVERED]),
            "random_over_learned": _ratio(
                eval_dict[f"{regime}/random_in_horizon"][RECOVERED], learned),
        }

    return {
        "regimes": list(REGIME_ORDER),
        "policies": list(POLICY_ORDER),
        "live_policies": list(LIVE_POLICIES),
        "precomputed_policies": list(PRECOMPUTED_POLICIES),
        "industry_baseline": INDUSTRY_BASELINE,
        "cells": cells,
        "headline": headline,
        "totals": {
            "cells": len(cells),
            "compliance_violations": sum(c["compliance_violations"] for c in cells.values()),
            "parked_paise": sum(c["parked_paise"] for c in cells.values()),
        },
        "provenance": _provenance(seeds, customers),
    }


def build_cliff(executions_by_policy: dict[str, list[dict]], *, regime: str,
                seeds: list[int], customers: int) -> dict:
    """Audit records -> retries-per-day-of-month and the win rate per day.

    This is the chart the whole negative result rests on: the model's retries
    pile up on days 21-23 while success in r1_shifted is a step function at
    day 25. Days with no retries carry a null win rate rather than 0.0, so the
    chart cannot invent a cliff out of missing data.
    """
    days = list(range(1, EVAL_HORIZON_HOURS // HOURS_PER_DAY + 1))
    index = {day: i for i, day in enumerate(days)}

    series: dict[str, dict] = {}
    for policy, records in executions_by_policy.items():
        tried = [0] * len(days)
        won = [0] * len(days)
        for record in records:
            if record.get("event") != "execution":
                continue
            at_hour = record["at_hour"]
            if at_hour >= EVAL_HORIZON_HOURS:
                # BROKELOG 2026-09-02: these were free wins against a balance
                # the simulator never modelled. evaluate.py no longer produces
                # them; refuse to chart one if it ever reappears.
                raise ValueError(
                    f"{policy}: execution at hour {at_hour} (day {at_hour // HOURS_PER_DAY}) "
                    f"is past the evaluated window of {EVAL_HORIZON_HOURS} hours"
                )
            i = index[day_of_month(at_hour)]
            tried[i] += 1
            won[i] += record["outcome"] == "success"
        series[policy] = {
            "tried": tried,
            "won": won,
            "win_rate": [won[i] / tried[i] if tried[i] else None for i in range(len(days))],
            "total_tried": sum(tried),
            "total_won": sum(won),
        }

    # The success rate is a property of the world, not of a policy: both
    # policies face the same step function at day 25. Pooling them gives the
    # chart one honest "what did day N pay out" line instead of two nearly
    # identical ones, and makes the pre/post-cliff contrast the only thing the
    # eye has to compare.
    pooled_tried = [sum(s["tried"][i] for s in series.values()) for i in range(len(days))]
    pooled_won = [sum(s["won"][i] for s in series.values()) for i in range(len(days))]

    return {
        "regime": regime,
        "days": days,
        "series": series,
        "pooled": {
            "tried": pooled_tried,
            "won": pooled_won,
            "win_rate": [pooled_won[i] / pooled_tried[i] if pooled_tried[i] else None
                         for i in range(len(days))],
        },
        "provenance": _provenance(seeds, customers),
    }
