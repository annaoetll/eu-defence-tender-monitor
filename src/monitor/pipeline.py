"""Daily run: fetch, validate, merge, write the run log and build the page."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .clean import COLUMNS, clean
from .dashboard import build_page
from .store import merge, read_rows, write_rows
from .ted import FIELDS, TedError, fetch_notices

ROOT = Path(__file__).resolve().parents[2]
QUARANTINE_COLUMNS = ["publication_number", "reason"]
MAX_QUARANTINE_SHARE = 0.2


def field_coverage(raw: list[dict]) -> dict[str, float]:
    """Share of notices carrying each field. A sudden 0 reveals a changed API."""
    if not raw:
        return {}
    return {f: round(sum(n.get(f) not in (None, "", [], {}) for n in raw) / len(raw), 3) for f in FIELDS}


def run(days: int, data_dir: Path, site_dir: Path) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()
    since: date = today - timedelta(days=days)
    raw, reported_total = fetch_notices(since, today)

    # Stop before touching any published file if the download is incomplete.
    if reported_total is not None and len(raw) < reported_total:
        raise TedError(f"Received {len(raw)} of {reported_total} notices")

    rows, quarantine = clean(raw)
    if raw and len(quarantine) / len(raw) > MAX_QUARANTINE_SHARE:
        raise TedError(f"{len(quarantine)} of {len(raw)} notices failed validation: {quarantine[:3]}")

    stamp = now.isoformat(timespec="seconds")
    data_dir.mkdir(exist_ok=True)
    notices_path = data_dir / "notices.csv"
    merged, added, updated = merge(read_rows(notices_path), rows, stamp)
    write_rows(notices_path, merged, COLUMNS)
    write_rows(data_dir / "quarantine.csv", quarantine, QUARANTINE_COLUMNS)

    log = {
        "finished_at": stamp,
        "window_start": since.isoformat(),
        "window_end": today.isoformat(),
        "reported_by_ted": reported_total,
        "received": len(raw),
        "valid": len(rows),
        "quarantined": len(quarantine),
        "added": added,
        "changed": updated,
        "total_in_dataset": len(merged),
        "field_coverage": field_coverage(raw),
    }
    (data_dir / "run_log.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    build_page(data_dir, site_dir)
    return log


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="days to re-query; overlap catches corrections")
    args = parser.parse_args()
    try:
        log = run(args.days, ROOT / "data", ROOT / "site")
    except (TedError, OSError) as error:  # requests errors derive from OSError
        print(f"Pipeline failed, published data left unchanged: {error}", file=sys.stderr)
        return 1
    print(json.dumps(log, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
