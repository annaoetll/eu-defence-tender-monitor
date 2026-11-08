"""Merge rows into data/notices.csv. Files are replaced atomically."""
from __future__ import annotations

import csv
import os
from pathlib import Path

from .clean import COLUMNS


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict], columns: list[str]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def merge(existing: list[dict], new: list[dict], retrieved_at: str) -> tuple[list[dict], int, int]:
    """Upsert on publication number. Returns merged rows, added count, updated count."""
    by_number = {row["publication_number"]: row for row in existing}
    added = updated = 0
    for row in new:
        old = by_number.get(row["publication_number"])
        record = {k: "" if row.get(k) is None else row.get(k, "") for k in COLUMNS}
        if old is None:
            added += 1
            record["first_retrieved_at"] = retrieved_at
        else:
            record["first_retrieved_at"] = old.get("first_retrieved_at", retrieved_at)
            fields = [c for c in COLUMNS if not c.endswith("retrieved_at")]
            updated += any(str(old.get(c, "")) != str(record[c]) for c in fields)
        record["last_retrieved_at"] = retrieved_at
        by_number[row["publication_number"]] = record
    merged = sorted(
        by_number.values(),
        key=lambda r: (str(r["publication_date"]), r["publication_number"]),
        reverse=True,
    )
    return merged, added, updated
