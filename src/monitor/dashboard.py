"""Build the static dashboard. No external scripts, styles or tracking."""
from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from html import escape
from pathlib import Path

from .store import read_rows

MIN_N = 10  # Countries with fewer award notices are left out of the rate chart.
COUNTRIES = {
    "AUT": "Austria", "BEL": "Belgium", "BGR": "Bulgaria", "HRV": "Croatia", "CYP": "Cyprus",
    "CZE": "Czechia", "DNK": "Denmark", "EST": "Estonia", "FIN": "Finland", "FRA": "France",
    "DEU": "Germany", "GRC": "Greece", "HUN": "Hungary", "IRL": "Ireland", "ITA": "Italy",
    "LVA": "Latvia", "LTU": "Lithuania", "LUX": "Luxembourg", "MLT": "Malta", "NLD": "Netherlands",
    "POL": "Poland", "PRT": "Portugal", "ROU": "Romania", "SVK": "Slovakia", "SVN": "Slovenia",
    "ESP": "Spain", "SWE": "Sweden", "NOR": "Norway", "GBR": "United Kingdom", "CHE": "Switzerland",
    "ISL": "Iceland", "LIE": "Liechtenstein",
}

CSS = """
:root{color-scheme:light;--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e4e3de;--mark:#2a78d6;--track:#efeeea}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#3a3a37;--mark:#3987e5;--track:#2b2b29}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:920px;margin:auto;padding:40px 16px 64px}
h1{font-size:2rem;line-height:1.15;margin:0 0 8px;letter-spacing:-.02em}
h2{font-size:1.15rem;margin:0 0 4px}
.sub,.note{color:var(--ink2)}.sub{margin:0 0 8px;max-width:680px}.note{font-size:.875rem;margin:0 0 14px}
.meta{font-size:.875rem;color:var(--ink2);margin:0}
a{color:inherit}
.banner{border:2px solid var(--ink);padding:8px 12px;margin:0 0 20px;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:32px 0;padding:20px 0;border-block:1px solid var(--line)}
.kpi b{display:block;font-size:1.85rem;line-height:1.1;font-variant-numeric:tabular-nums}
.kpi span{font-size:.85rem;color:var(--ink2)}
section{margin:40px 0}
.two{display:grid;grid-template-columns:1fr 1fr;gap:32px}.two section{margin:0}
.row{display:grid;grid-template-columns:150px 1fr 76px;gap:10px;align-items:center;padding:3px 0;font-size:.9rem;border-radius:4px}
.row:hover,.row:focus{background:var(--track);outline:none}
.track{height:10px}.fill{display:block;height:100%;min-width:2px;background:var(--mark);border-radius:0 4px 4px 0}
.val{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink2);white-space:nowrap}
.cols{display:flex;align-items:flex-end;gap:2px;height:150px;border-bottom:1px solid var(--line)}
.col{flex:1;height:100%;display:flex;align-items:flex-end}.col:hover,.col:focus{background:var(--track);outline:none}
.col i{display:block;width:100%;min-height:2px;background:var(--mark);border-radius:4px 4px 0 0}
.col.partial i{background:repeating-linear-gradient(135deg,var(--mark) 0 3px,var(--track) 3px 6px)}
.axis{display:flex;justify-content:space-between;font-size:.8rem;color:var(--ink2);margin-top:4px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.875rem}
th,td{text-align:left;padding:7px 10px 7px 0;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--ink2);font-weight:500}.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
ul{padding-left:20px}li{margin:6px 0}
#tip{position:fixed;display:none;pointer-events:none;background:var(--ink);color:var(--bg);padding:4px 8px;border-radius:4px;font-size:.8rem}
@media (max-width:680px){.kpis{grid-template-columns:1fr 1fr}.two{grid-template-columns:1fr}.row{grid-template-columns:105px 1fr 66px}}
"""

JS = """
const t=document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(e=>{
 const show=(x,y)=>{t.textContent=e.dataset.tip;t.style.display='block';
  t.style.left=Math.max(8,Math.min(x+12,innerWidth-t.offsetWidth-8))+'px';t.style.top=(y-34)+'px'};
 e.addEventListener('mousemove',v=>show(v.clientX,v.clientY));
 e.addEventListener('mouseleave',()=>t.style.display='none');
 e.addEventListener('focus',()=>{const r=e.getBoundingClientRect();show(r.left,r.top)});
 e.addEventListener('blur',()=>t.style.display='none');
});
"""


def _country(code: str) -> str:
    return COUNTRIES.get(code, code)


def _yes(row: dict, key: str) -> bool:
    return str(row.get(key)).lower() == "true"


def _countries(row: dict) -> list[str]:
    return [c for c in row.get("buyer_country", "").split(";") if c]


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def _bars(items: list[tuple[str, float, str, str]], maximum: float) -> str:
    """Rows of (label, value, shown value, tooltip)."""
    out = []
    for label, value, shown, tip in items:
        width = 100 * value / maximum if maximum else 0
        out.append(
            f'<div class="row" tabindex="0" data-tip="{escape(tip)}"><span>{escape(label)}</span>'
            f'<span class="track"><span class="fill" style="width:{width:.1f}%"></span></span>'
            f'<span class="val">{escape(shown)}</span></div>'
        )
    return "".join(out)


def _months(rows: list[dict], latest_date: str) -> str:
    counts = Counter(r["publication_date"][:7] for r in rows)
    if not counts:
        return ""
    months = sorted(counts)[-24:]
    current = latest_date[:7]
    peak = max(counts[m] for m in months)
    cols = "".join(
        f'<div class="col{" partial" if m == current else ""}" tabindex="0" '
        f'data-tip="{m}: {counts[m]} notices{" (month in progress)" if m == current else ""}">'
        f'<i style="height:{100 * counts[m] / peak:.1f}%"></i></div>'
        for m in months
    )
    return f'<div class="cols">{cols}</div><div class="axis"><span>{months[0]}</span><span>peak {peak} per month</span><span>{months[-1]}</span></div>'


def _manual_check(path: Path) -> str:
    if not path.exists():
        return "Manual check against TED: not yet done."
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    checked = [r for r in rows if r.get("matches_source", "").strip().lower() in ("yes", "no")]
    if not checked:
        return "Manual check against TED: sample drawn, not yet done."
    ok = sum(r["matches_source"].strip().lower() == "yes" for r in checked)
    return f"Manual check against TED: {ok} of {len(checked)} sampled records match the source."


def render(rows: list[dict], log: dict, check_text: str, banner: str | None = None) -> str:
    awards = [r for r in rows if r.get("form_type") == "result"]
    with_value = sum(_yes(r, "value_disclosed") for r in awards)
    with_winner = sum(_yes(r, "winner_disclosed") for r in awards)
    latest = max((r["publication_date"] for r in rows), default="")
    earliest = min((r["publication_date"] for r in rows), default="")

    country_counts = Counter(c for r in rows for c in _countries(r))
    top = country_counts.most_common(10)
    country_bars = _bars(
        [(_country(c), n, str(n), f"{_country(c)}: {n} notices") for c, n in top], top[0][1] if top else 0
    )
    groups = Counter(r["cpv_group"] for r in rows).most_common()
    group_bars = _bars([(g, n, str(n), f"{g}: {n} notices") for g, n in groups], groups[0][1] if groups else 0)

    by_country: dict[str, list[dict]] = {}
    for row in awards:
        for code in _countries(row):
            by_country.setdefault(code, []).append(row)
    rates = sorted(
        ((c, sum(_yes(r, "value_disclosed") for r in rs), len(rs)) for c, rs in by_country.items() if len(rs) >= MIN_N),
        key=lambda x: (-x[1] / x[2], x[0]),
    )
    rate_bars = _bars(
        [(_country(c), 100 * k / n, _pct(k, n), f"{_country(c)}: {k} of {n} award notices state a value") for c, k, n in rates],
        100,
    ) or f'<p class="note">Not enough data yet: no country has {MIN_N} award notices.</p>'

    table = "".join(
        f'<tr><td style="white-space:nowrap">{escape(r["publication_date"])}</td><td>{escape(_country(_countries(r)[0]) if _countries(r) else "")}</td>'
        f'<td>{escape(r["cpv_group"])}</td><td>{escape(r["buyer_name"][:70])}</td><td>{escape(r["form_type"])}</td>'
        f'<td><a href="{escape(r["source_url"], quote=True)}">{escape(r["publication_number"])}</a></td></tr>'
        for r in rows[:20]
    )
    banner_html = f'<p class="banner">{escape(banner)}</p>' if banner else ""
    run = (
        f'Last run {escape(str(log.get("finished_at", "n/a")))}: TED reported {escape(str(log.get("reported_by_ted", "n/a")))} notices in the query window, '
        f'{escape(str(log.get("received", "n/a")))} received, {escape(str(log.get("valid", "n/a")))} valid, {escape(str(log.get("quarantined", "n/a")))} quarantined.'
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EU Defence Tender Monitor</title><style>{CSS}</style></head><body><main>
{banner_html}<h1>EU Defence Tender Monitor</h1>
<p class="sub">A daily snapshot of military procurement notices published on the EU's Tenders Electronic Daily (TED), and of how much those notices disclose.</p>
<p class="meta">Data from {escape(earliest or "n/a")} to {escape(latest or "n/a")}. <a href="notices.csv">Download the data (CSV)</a></p>
<div class="kpis">
<div class="kpi"><b>{len(rows):,}</b><span>notices</span></div>
<div class="kpi"><b>{len(country_counts)}</b><span>buyer countries</span></div>
<div class="kpi"><b>{_pct(with_value, len(awards))}</b><span>of {len(awards):,} award notices state a value</span></div>
<div class="kpi"><b>{_pct(with_winner, len(awards))}</b><span>of award notices name a winner</span></div>
</div>
<section><h2>Share of award notices stating a contract value</h2>
<p class="note">Countries with at least {MIN_N} award notices. A stated value of 0 counts as not stated.</p>{rate_bars}</section>
<section><h2>Notices published per month</h2><p class="note">Hatched bar: month still in progress.</p>{_months(rows, latest)}</section>
<div class="two"><section><h2>Notices by buyer country</h2><p class="note">Top 10.</p>{country_bars}</section>
<section><h2>Notices by equipment group</h2><p class="note">First military CPV code on each notice.</p>{group_bars}</section></div>
<section><h2>Latest notices</h2><div class="scroll"><table><thead><tr><th>Date</th><th>Buyer country</th><th>Group</th><th>Buyer</th><th>Form</th><th>Source</th></tr></thead><tbody>{table}</tbody></table></div></section>
<section><h2>What this data can and cannot show</h2><ul>
<li>This is not total European defence procurement. Many large purchases never appear on TED, for example under Article 346 TFEU or in government-to-government deals.</li>
<li>Notice counts measure publication activity, not spending. Values are not summed because currencies, frameworks and lot structures are not comparable without further work.</li>
<li>A notice can be a correction or a later stage of the same procedure, so notices are not unique purchases.</li>
<li>The filter uses CPV groups 353 to 358, so it misses defence purchases coded elsewhere and includes any notice that carries one of these codes.</li>
</ul></section>
<section><h2>Data quality</h2><p class="note">{run} {escape(check_text)} Every record links to its source notice. Independent project, not affiliated with TED or any research institute. Source: <a href="https://ted.europa.eu">TED</a>, © European Union.</p></section>
</main><div id="tip" role="status"></div><script>{JS}</script></body></html>"""


def build_page(data_dir: Path, site_dir: Path, banner: str | None = None) -> None:
    site_dir.mkdir(exist_ok=True)
    rows = read_rows(data_dir / "notices.csv")
    log_path = data_dir / "run_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    check_text = _manual_check(data_dir.parent / "docs" / "manual_check.csv")
    (site_dir / "index.html").write_text(render(rows, log, check_text, banner), encoding="utf-8")
    if (data_dir / "notices.csv").exists():
        shutil.copy(data_dir / "notices.csv", site_dir / "notices.csv")
