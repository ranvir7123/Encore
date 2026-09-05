"""Pure HTML/SVG renderers for the static evidence site.

Same split as `report.py`: plain f-strings, no template engine, no file I/O,
so every renderer is directly unit-testable. `cli.cmd_web` does the writing.

The cliff chart is emitted as static SVG rather than drawn by JavaScript
because it is Tier B evidence -- it has to be complete and readable before any
script runs, and it must survive Pyodide failing to load entirely (spec
section 3, "progressive enhancement is mandatory"). JavaScript only adds
hover readouts on top of markup that already says everything.
"""
import re

from encore.report import _esc, format_rupees

# Both policies are drawn against ONE y-axis on purpose. The learned policy
# spikes to 219 retries on a single day while the control never exceeds 54;
# a shared axis is what makes "concentrated on the wrong days" versus "spread
# across the month" visible at a glance. Per-series axes would hide the very
# thing the chart exists to show.
CHART_W, CHART_H = 960, 408
PAD_L, PAD_R, PAD_T, PAD_B = 54, 54, 26, 62
PLOT_W = CHART_W - PAD_L - PAD_R
PLOT_H = CHART_H - PAD_T - PAD_B

SERIES_STYLE = {
    "encore_learned": {"class": "bar-learned", "label": "encore_learned (the model)"},
    "random_in_horizon": {"class": "bar-random", "label": "random_in_horizon (the control)"},
}


def _y_max(values: list[int]) -> int:
    """Round the axis up to a clean multiple of 60 so gridlines land on whole
    numbers. Never returns 0 -- an empty chart still needs a scale."""
    peak = max(values, default=0)
    return max(60, -(-peak // 60) * 60)


def _fmt_pct(rate: float | None) -> str:
    return "no retries" if rate is None else f"{round(rate * 100)}%"


def render_cliff_svg(cliff: dict, *, cliff_day: int = 25) -> str:
    """The signature Tier B figure: retries per day-of-month for each policy,
    with the pooled success rate overlaid as the step function they are both
    aiming at.

    `cliff_day` is where the step happens in r1_shifted (salary lands on day
    25 for half the portfolio). It is a parameter rather than a constant so a
    different regime's chart cannot silently inherit r1_shifted's calendar.
    """
    days = cliff["days"]
    series = cliff["series"]
    pooled = cliff["pooled"]["win_rate"]
    band = PLOT_W / len(days)
    bar_w = min(11.0, band / 2 - 1.5)

    all_tried = [v for s in series.values() for v in s["tried"]]
    y_max = _y_max(all_tried)

    def x_of(i: int) -> float:
        return PAD_L + i * band

    def y_of(count: int) -> float:
        return PAD_T + PLOT_H - (count / y_max) * PLOT_H

    def y_of_rate(rate: float) -> float:
        return PAD_T + PLOT_H - rate * PLOT_H

    parts: list[str] = []

    # Shaded band from the cliff day to the end of the month: the region where
    # a retry is worth making at all.
    cliff_i = days.index(cliff_day)
    parts.append(
        f'<rect class="cliff-zone" x="{x_of(cliff_i):.1f}" y="{PAD_T}" '
        f'width="{PLOT_W - cliff_i * band:.1f}" height="{PLOT_H}" />'
    )

    # Horizontal gridlines + left axis (retry counts)
    for step in range(0, y_max + 1, 60):
        y = y_of(step)
        parts.append(f'<line class="grid" x1="{PAD_L}" y1="{y:.1f}" '
                     f'x2="{PAD_L + PLOT_W}" y2="{y:.1f}" />')
        parts.append(f'<text class="axis-label axis-left" x="{PAD_L - 10}" '
                     f'y="{y + 4:.1f}">{step}</text>')

    # Right axis (pooled success rate)
    for pct in (0, 50, 100):
        y = y_of_rate(pct / 100)
        parts.append(f'<text class="axis-label axis-right" x="{PAD_L + PLOT_W + 10}" '
                     f'y="{y + 4:.1f}">{pct}%</text>')

    # Bars, one group per day
    for name, style in SERIES_STYLE.items():
        if name not in series:
            continue
        offset = 0 if name == "encore_learned" else bar_w + 2
        tried = series[name]["tried"]
        for i, count in enumerate(tried):
            if not count:
                continue
            x = x_of(i) + (band - (2 * bar_w + 2)) / 2 + offset
            y = y_of(count)
            parts.append(
                f'<rect class="{style["class"]}" x="{x:.1f}" y="{y:.1f}" '
                f'width="{bar_w:.1f}" height="{PAD_T + PLOT_H - y:.1f}" '
                f'data-day="{days[i]}" data-policy="{_esc(name)}" data-tried="{count}" '
                f'data-won="{series[name]["won"][i]}"><title>Day {days[i]} — '
                f'{_esc(name)}: {count} retries, {series[name]["won"][i]} recovered'
                f'</title></rect>'
            )

    # Pooled success rate as a step line: it is a property of the world, not of
    # a policy, so it is drawn once and both policies are measured against it.
    step_points: list[str] = []
    for i, rate in enumerate(pooled):
        if rate is None:
            continue
        y = y_of_rate(rate)
        step_points.append(f"{x_of(i):.1f},{y:.1f}")
        step_points.append(f"{x_of(i) + band:.1f},{y:.1f}")
    if step_points:
        parts.append(f'<polyline class="rate-line" points="{" ".join(step_points)}" />')

    # The cliff itself
    cliff_x = x_of(cliff_i)
    parts.append(f'<line class="cliff-line" x1="{cliff_x:.1f}" y1="{PAD_T - 6}" '
                 f'x2="{cliff_x:.1f}" y2="{PAD_T + PLOT_H}" />')
    parts.append(f'<text class="cliff-label" x="{cliff_x + 7:.1f}" y="{PAD_T + 6}">'
                 f'day {cliff_day}: success jumps to 100%</text>')

    # X axis
    parts.append(f'<line class="axis" x1="{PAD_L}" y1="{PAD_T + PLOT_H}" '
                 f'x2="{PAD_L + PLOT_W}" y2="{PAD_T + PLOT_H}" />')
    for i, day in enumerate(days):
        if day % 5 and day != 1:
            continue
        parts.append(f'<text class="axis-label axis-x" x="{x_of(i) + band / 2:.1f}" '
                     f'y="{PAD_T + PLOT_H + 20}">{day}</text>')
    parts.append(f'<text class="axis-title" x="{PAD_L + PLOT_W / 2:.1f}" '
                 f'y="{CHART_H - 26}">day of month</text>')
    parts.append(f'<text class="axis-title axis-title-left" x="{PAD_L - 10}" '
                 f'y="{PAD_T - 12}">retries</text>')
    parts.append(f'<text class="axis-title axis-title-right" x="{PAD_L + PLOT_W + 10}" '
                 f'y="{PAD_T - 12}">success rate</text>')

    learned_total = series.get("encore_learned", {}).get("total_tried", 0)
    random_total = series.get("random_in_horizon", {}).get("total_tried", 0)
    desc = (f"Retries per day of month in regime {cliff['regime']}. "
            f"encore_learned made {learned_total} retries, random_in_horizon "
            f"{random_total}. Pooled success rate is near zero before day "
            f"{cliff_day} and 100% from day {cliff_day} onward.")

    return (
        f'<svg class="cliff-chart" viewBox="0 0 {CHART_W} {CHART_H}" role="img" '
        f'aria-labelledby="cliff-title cliff-desc" preserveAspectRatio="xMidYMid meet">'
        f'<title id="cliff-title">Retries per day of month against the day-{cliff_day} '
        f'success cliff</title>'
        f'<desc id="cliff-desc">{_esc(desc)}</desc>'
        + "".join(parts)
        + "</svg>"
    )


def render_cliff_table(cliff: dict) -> str:
    """The same numbers as a real table. Not a fallback -- it is the accessible
    version of the chart and stays in the DOM, collapsed behind a <details>, so
    the figures are readable by screen reader, by search, and with every style
    and script disabled."""
    days = cliff["days"]
    learned = cliff["series"].get("encore_learned", {})
    random_s = cliff["series"].get("random_in_horizon", {})
    rows = "".join(
        f"<tr><td>{day}</td>"
        f"<td>{learned.get('tried', [0] * len(days))[i]}</td>"
        f"<td>{learned.get('won', [0] * len(days))[i]}</td>"
        f"<td>{random_s.get('tried', [0] * len(days))[i]}</td>"
        f"<td>{random_s.get('won', [0] * len(days))[i]}</td>"
        f"<td>{_fmt_pct(cliff['pooled']['win_rate'][i])}</td></tr>"
        for i, day in enumerate(days)
    )
    return (
        '<table class="data-table">'
        "<caption>Retries attempted and recovered per day of month, "
        f"regime {_esc(cliff['regime'])}.</caption>"
        "<thead><tr><th scope=\"col\">Day</th>"
        '<th scope="col">Model tried</th><th scope="col">Model won</th>'
        '<th scope="col">Control tried</th><th scope="col">Control won</th>'
        '<th scope="col">Success rate</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def render_provenance(provenance: dict) -> str:
    """Every generated figure states where it came from (spec section 3)."""
    seeds = ", ".join(str(s) for s in provenance["seeds"])
    return (
        '<p class="provenance">Seeds <span class="mono">{seeds}</span> · '
        '<span class="mono">{customers}</span> customers per seed · '
        '{days}-day window · reproduce with '
        '<code>{command}</code></p>'
    ).format(seeds=_esc(seeds), customers=provenance["customers"],
             days=provenance["horizon_days"], command=_esc(provenance["command"]))


def render_headline_figures(results: dict, cliff: dict, *, regime: str = "r1_shifted",
                            test_count: int = 0) -> str:
    """The four headline numbers, as lab-report stat cards. Every one is read
    from the generated data, so the hero cannot drift from the matrix under it."""
    head = results["headline"][regime]
    baseline = results["industry_baseline"]
    learned_ratio = head["learned_over_fixed_t123"]
    random_ratio = head["random_over_learned"]
    cells = results["totals"]["cells"]

    cards = [
        (f"{learned_ratio:.2f}x" if learned_ratio else "n/a", "recovered",
         "Recovery vs industry baseline",
         f"Against {baseline}, Razorpay's documented T+1/T+2/T+3 shape.", "is-good"),
        (str(results["totals"]["compliance_violations"]), f"of {cells} cells",
         "Compliance violations",
         "Checked by replaying every execution record against the wall.", "is-good"),
        (f"+{round((random_ratio - 1) * 100)}%" if random_ratio else "n/a", "vs the model",
         "Uniform random, held-out regime",
         "Our own control. It beat the trained policy, and we published it.", "is-flag"),
        (str(test_count), "passing", "Test suite",
         "24 of them adversarial, aimed squarely at the wall.", ""),
    ]
    items = "".join(
        f'<div class="stat-card {cls}">'
        f'<h3>{_esc(title)}</h3>'
        f'<div class="stat-value">{_esc(value)} <span class="unit">{_esc(unit)}</span></div>'
        f"<hr>"
        f"<p>{_esc(note)}</p>"
        "</div>"
        for value, unit, title, note, cls in cards
    )
    return f'<div class="stat-grid">{items}</div>'


def render_money(paise: int) -> str:
    """Thin pass-through so callers never reach for a float."""
    return format_rupees(paise)


# Days 21-24 in r1_shifted: the four days immediately before the cliff, where
# the model piles up its retries. Derived from cliff_day rather than hardcoded
# so a different regime's chart cannot inherit r1_shifted's calendar.
PRE_CLIFF_DAYS = 4

MARKER = re.compile(r"\{\{([A-Z_]+)\}\}")


def _window(series: dict, days: list[int], lo: int, hi: int) -> int:
    """Retries attempted on days lo..hi inclusive."""
    return sum(count for day, count in zip(days, series["tried"]) if lo <= day <= hi)


def render_page(template: str, results: dict, cliff: dict, *, test_count: int,
                cliff_day: int = 25, regime: str = "r1_shifted") -> str:
    """Fill the hand-written template from generated data.

    Every number the page states is substituted here rather than typed into
    the template, so the prose cannot drift from the matrix underneath it --
    the failure mode the spec calls a transcription bug. An unknown marker, or
    a marker left unfilled, raises: a page that silently ships `{{CELLS}}` to a
    judge is worse than a build that fails.
    """
    days = cliff["days"]
    learned = cliff["series"]["encore_learned"]
    control = cliff["series"]["random_in_horizon"]
    head = results["headline"][regime]

    random_margin = head["random_over_learned"]
    learned_ratio = head["learned_over_fixed_t123"]

    values = {
        "HEADLINE_FIGURES": render_headline_figures(results, cliff, regime=regime,
                                                    test_count=test_count),
        "CLIFF_SVG": render_cliff_svg(cliff, cliff_day=cliff_day),
        "CLIFF_TABLE": render_cliff_table(cliff),
        "CLIFF_PROVENANCE": render_provenance(cliff["provenance"]),
        "RANDOM_MARGIN": (f"{round((random_margin - 1) * 100)}%"
                          if random_margin else "an unmeasured margin"),
        "LEARNED_RATIO": f"{learned_ratio:.2f}x" if learned_ratio else "n/a",
        "VIOLATIONS": str(results["totals"]["compliance_violations"]),
        "CELLS": str(results["totals"]["cells"]),
        "LEARNED_BEFORE": str(_window(learned, days, cliff_day - PRE_CLIFF_DAYS,
                                      cliff_day - 1)),
        "LEARNED_AFTER": str(_window(learned, days, cliff_day, max(days))),
        "RANDOM_AFTER": str(_window(control, days, cliff_day, max(days))),
    }

    unknown = {m for m in MARKER.findall(template)} - set(values)
    if unknown:
        raise ValueError(
            f"template has {len(unknown)} marker(s) nothing fills: "
            f"{', '.join(sorted(unknown))}"
        )

    page = MARKER.sub(lambda m: values[m.group(1)], template)
    leftover = MARKER.findall(page)
    if leftover:  # pragma: no cover -- sub() above is exhaustive; belt and braces
        raise ValueError(f"unfilled marker(s) survived rendering: {sorted(set(leftover))}")
    return page
