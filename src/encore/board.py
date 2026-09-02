"""Live recovery board: a pure transform over the agent's audit records and an
f-string HTML page, rewritten on every agent tick. No JavaScript, no server,
no template engine -- the same discipline as report.py's scoreboard. The page
refreshes itself, so a browser left open on runs/board.html shows the
counters move as links get paid."""
import os
from pathlib import Path

from encore.report import _esc, format_rupees

LIVE_RAIL = "razorpay_test_mode"


def _row(customer_id: str, amount_paise: int) -> dict:
    return {"customer_id": customer_id, "amount_paise": amount_paise, "rail": "simulated",
            "last_event": "detected", "link_id": None, "short_url": None, "status": None}


def build_board(records: list[dict], at_risk_by_customer: dict[str, int]) -> dict:
    customers = {cid: _row(cid, amt) for cid, amt in at_risk_by_customer.items()}
    recovered = attempts = nudges = replies = 0
    denials: dict[str, int] = {}
    parked: dict[str, int] = {}
    open_links: set[str] = set()
    for r in records:
        ev = r.get("event")
        cid = r.get("customer_id")
        row = customers.get(cid) if cid else None
        if row is None and cid:
            row = customers[cid] = _row(cid, int(r.get("amount_paise", 0)))
        if ev == "nudge":
            nudges += 1
            row["last_event"] = "nudged"
        elif ev == "reply":
            replies += 1
            row["last_event"] = f"replied: {r.get('kind')}"
        elif ev == "decision":
            if r.get("allowed"):
                if r.get("kind") == "retry" and not r.get("probe"):
                    row["last_event"] = "scheduled"
            else:
                denials[r["reason"]] = denials.get(r["reason"], 0) + 1
        elif ev == "link_created":
            open_links.add(r["attempt_id"])
            row.update(rail=r.get("rail", LIVE_RAIL), link_id=r.get("link_id"),
                       short_url=r.get("short_url"), status=r.get("status"),
                       last_event="link_created")
        elif ev == "execution":
            attempts += 1
            open_links.discard(r.get("attempt_id"))
            row["rail"] = r.get("rail", row["rail"])
            if r.get("link_id"):
                row.update(link_id=r["link_id"], short_url=r.get("short_url"),
                           status=r.get("status"))
            if r.get("outcome") == "success":
                recovered += int(r["amount_paise"])
                row["last_event"] = "recovered"
            else:
                row["last_event"] = f"failed attempt {r.get('attempt_no', '?')}"
        elif ev == "park":
            parked[r["reason"]] = parked.get(r["reason"], 0) + 1
            row["last_event"] = f"parked: {r['reason']}"
        elif ev == "duplicate_blocked":
            row["last_event"] = "duplicate_blocked"
    ordered = sorted(customers.values(), key=lambda c: (c["rail"] != LIVE_RAIL, c["customer_id"]))
    at_risk = sum(at_risk_by_customer.values())
    return {
        "at_risk_paise": at_risk,
        "recovered_paise": recovered,
        "recovery_rate": (recovered / at_risk) if at_risk else 0.0,  # display only
        "in_flight": len(open_links),
        "attempts": attempts,
        "nudges": nudges,
        "replies": replies,
        "denials": dict(sorted(denials.items())),
        "parked": dict(sorted(parked.items())),
        "customers": ordered,
    }


_CSS = """
body{margin:0;background:#fcf8f9;color:#1b1b1c;font:15px/1.45 'IBM Plex Sans',system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 20px 60px}
h1{font:600 26px/1.2 'IBM Plex Serif',Georgia,serif;color:#000d2f;margin:0 0 4px}
.prov{color:#757681;font:13px 'IBM Plex Mono',ui-monospace,monospace;margin-bottom:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:24px}
.card{border:1px solid #d8d9de;border-radius:8px;padding:12px 14px;background:#fff}
.card .k{font-size:12px;color:#757681;text-transform:uppercase;letter-spacing:.04em}
.card .v{font:600 22px/1.2 'IBM Plex Mono',ui-monospace,monospace;color:#00205b;margin-top:4px}
.card.win .v{color:#1b6b2a}
h2{font:600 16px 'IBM Plex Serif',Georgia,serif;color:#000d2f;margin:20px 0 8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid #e6e6ea;text-align:left;vertical-align:top}
th{color:#757681;font-weight:500}
td.num,th.num{text-align:right;font-family:'IBM Plex Mono',ui-monospace,monospace}
.live{color:#8a2be2;font-weight:600}
.ok{color:#1b6b2a}.bad{color:#ac3231}
.wrap{overflow-x:auto}
a{color:#00205b}
"""


def _reason_table(title: str, counts: dict[str, int]) -> str:
    if not counts:
        return f"<h2>{_esc(title)}</h2><p>none</p>"
    rows = "".join(f"<tr><td>{_esc(k)}</td><td class='num'>{v}</td></tr>" for k, v in counts.items())
    return f"<h2>{_esc(title)}</h2><div class='wrap'><table><tr><th>reason</th><th class='num'>count</th></tr>{rows}</table></div>"


def render_board(data: dict, provenance: str, refresh_s: int = 3) -> str:
    cards = [
        ("At risk", format_rupees(data["at_risk_paise"]), ""),
        ("Recovered", format_rupees(data["recovered_paise"]), "win"),
        ("Recovery rate", f"{data['recovery_rate'] * 100:.1f}%", ""),
        ("Links in flight", str(data["in_flight"]), ""),
        ("Attempts", str(data["attempts"]), ""),
        ("Nudges / replies", f"{data['nudges']} / {data['replies']}", ""),
    ]
    card_html = "".join(f"<div class='card {cls}'><div class='k'>{_esc(k)}</div>"
                        f"<div class='v'>{_esc(v)}</div></div>" for k, v, cls in cards)
    rows = []
    for c in data["customers"]:
        ev = c["last_event"]
        cls = "ok" if ev == "recovered" else ("bad" if ev.startswith("parked") else "")
        rail = (f"<span class='live'>{_esc(c['rail'])}</span>" if c["rail"] == LIVE_RAIL
                else _esc(c["rail"]))
        link = (f"<a href='{_esc(c['short_url'])}'>{_esc(c['link_id'])}</a>"
                if c.get("short_url") else _esc(c.get("link_id") or ""))
        rows.append(f"<tr><td>{_esc(c['customer_id'])}</td><td class='num'>"
                    f"{_esc(format_rupees(c['amount_paise']))}</td><td>{rail}</td>"
                    f"<td class='{cls}'>{_esc(ev)}</td><td>{link}</td>"
                    f"<td>{_esc(c.get('status') or '')}</td></tr>")
    customers_html = ("<div class='wrap'><table><tr><th>customer</th><th class='num'>amount</th>"
                      "<th>rail</th><th>last event</th><th>link</th><th>status</th></tr>"
                      + "".join(rows) + "</table></div>")
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
        f"<meta http-equiv=\"refresh\" content=\"{int(refresh_s)}\">"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Encore recovery board</title><style>{_CSS}</style></head><body><main>"
        "<h1>Encore recovery board</h1>"
        f"<div class='prov'>{_esc(provenance)}</div>"
        f"<div class='cards'>{card_html}</div>"
        + _reason_table("Wall denials", data["denials"])
        + _reason_table("Parked (exceptions the agent will not chase)", data["parked"])
        + "<h2>Customers</h2>" + customers_html
        + "</main></body></html>\n"
    )


def write_board(path: Path, data: dict, provenance: str, refresh_s: int = 3) -> None:
    """Write to a sibling temp file then os.replace, so a browser refresh never
    reads a half-written page."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(render_board(data, provenance, refresh_s), encoding="utf-8")
    os.replace(tmp, path)
