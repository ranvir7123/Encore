"""Task 12: static HTML scoreboard. Builds the page with plain f-strings --
no template engine dependency, per the brief. All money stays integer paise
until format_rupees() is called at the very last moment, right before a
number is dropped into an HTML string.
"""
import glob
import html
import json
from pathlib import Path

from encore.audit import AuditLog


def _esc(value: object) -> str:
    """Escape a dynamic (audit-log- or eval.json-derived) value before it is
    interpolated into the HTML string -- these values ultimately trace back
    to customer replies and simulator-generated ids, not to a fixed set of
    strings this module controls.
    """
    return html.escape(str(value))


def format_rupees(paise: int) -> str:
    """paise -> "Rs1,50,291.50" using Indian digit grouping (last 3 digits,
    then pairs), not western thousands-grouping. Chosen because this is an
    INR/Razorpay product (see docs/spike-notes.md) -- lakhs/crores grouping
    is the reader's native convention, not an arbitrary pick.
    """
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    whole, frac = divmod(paise, 100)
    s = str(whole)
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        grouped = ",".join([*groups, last3])
    return f"₹{sign}{grouped}.{frac:02d}"


def _table_rows(eval_dict: dict) -> str:
    rows = []
    for cell, metrics in sorted(eval_dict.items()):
        regime, policy = cell.split("/", 1)
        rows.append(
            "<tr>"
            f"<td>{_esc(regime)}</td><td>{_esc(policy)}</td>"
            f"<td>{format_rupees(metrics['recovered_per_1000_failures_paise'])}</td>"
            f"<td>{format_rupees(metrics['recovery_per_attempt_paise'])}</td>"
            f"<td>{metrics['max_contacts_per_customer']}</td>"
            f"<td>{format_rupees(metrics['parked_paise'])}</td>"
            f"<td>{metrics['compliance_violations']}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _denial_breakdown(eval_dict: dict) -> str:
    totals: dict[str, int] = {}
    for metrics in eval_dict.values():
        for reason, count in metrics.get("denials_by_reason", {}).items():
            totals[reason] = totals.get(reason, 0) + count
    if not totals:
        return "<p>No denials recorded.</p>"
    items = "\n".join(
        f"<li>{_esc(reason)}: {count}</li>" for reason, count in sorted(totals.items())
    )
    return f"<ul>{items}</ul>"


def _audit_trail_section(audit_sample: tuple[str, list[dict]] | None) -> str:
    if audit_sample is None:
        return (
            '<p id="audit-trail-missing">No audit log found -- '
            "run `encore eval` first to generate one.</p>"
        )
    customer_id, records = audit_sample
    rows = "\n".join(
        "<tr>"
        f"<td>{_esc(r.get('event', ''))}</td>"
        f"<td>{_esc(r.get('at_hour', ''))}</td>"
        f"<td>{_esc(r.get('kind', r.get('outcome', '')))}</td>"
        f"<td>{_esc(r.get('reason', r.get('original_decline', '')))}</td>"
        f"<td>{_esc(r.get('attempt_id', ''))}</td>"
        "</tr>"
        for r in records
    )
    return (
        f"<p>Sample customer: <code>{_esc(customer_id)}</code></p>"
        "<table><thead><tr><th>event</th><th>at_hour</th><th>kind/outcome</th>"
        "<th>reason/decline</th><th>attempt_id</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def render(eval_dict: dict, audit_sample: tuple[str, list[dict]] | None = None) -> str:
    """Build the scoreboard page as a plain string. Pure function: no file
    I/O, so it is directly unit-testable against a fixture eval dict.
    """
    total_parked = sum(m["parked_paise"] for m in eval_dict.values())
    total_violations = sum(m["compliance_violations"] for m in eval_dict.values())

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Encore Scoreboard</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
table {{ border-collapse: collapse; margin: 1rem 0; }}
th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: left; }}
th {{ background: #f2f2f2; }}
.violations {{ font-weight: bold; }}
.parked {{ font-weight: bold; }}
</style>
</head>
<body>
<h1>Encore Scoreboard</h1>

<h2>Policy &times; Regime</h2>
<table>
<thead><tr>
<th>Regime</th><th>Policy</th><th>Recovered / 1000 failures</th>
<th>Recovery / attempt</th><th>Max contacts / customer</th>
<th>Parked</th><th>Violations</th>
</tr></thead>
<tbody>
{_table_rows(eval_dict)}
</tbody>
</table>

<h2>Denial-reason breakdown</h2>
{_denial_breakdown(eval_dict)}

<p class="parked">Total parked revenue: {format_rupees(total_parked)}</p>
<p class="violations">Violations: {total_violations}</p>

<h2>Sample audit trail</h2>
{_audit_trail_section(audit_sample)}

</body>
</html>
"""


def find_sample_audit_file(audit_dir: Path) -> Path | None:
    """Pick the first r1_shifted/encore_learned audit file (sorted by seed)
    that actually contains an execution record. r1_shifted is the held-out
    distribution-shift regime, and encore_learned is the policy of interest
    -- see evaluate.py's REGIMES docstring.
    """
    audit_dir = Path(audit_dir)
    candidates = sorted(glob.glob(str(audit_dir / "r1_shifted__encore_learned__s*_audit.jsonl")))
    for candidate in candidates:
        path = Path(candidate)
        records = AuditLog(path).read_all()
        if any(r.get("event") == "execution" for r in records):
            return path
    return None


def sample_customer_trail(audit_path: Path) -> tuple[str, list[dict]] | None:
    """Full record trail for the first customer with an execution event in
    audit_path, in file order.
    """
    records = AuditLog(Path(audit_path)).read_all()
    for record in records:
        if record.get("event") == "execution":
            customer_id = record["customer_id"]
            trail = [r for r in records if r.get("customer_id") == customer_id]
            return customer_id, trail
    return None


def write_scoreboard(eval_path: Path, out_path: Path, audit_dir: Path) -> Path:
    """Read eval_path (runs/eval.json), write out_path (runs/scoreboard.html).
    Must never crash on missing audit artifacts -- find_sample_audit_file
    returns None and render() renders the "run `encore eval` first"
    placeholder instead.
    """
    eval_dict = json.loads(Path(eval_path).read_text(encoding="utf-8"))

    audit_sample = None
    audit_file = find_sample_audit_file(Path(audit_dir))
    if audit_file is not None:
        audit_sample = sample_customer_trail(audit_file)

    html = render(eval_dict, audit_sample=audit_sample)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
