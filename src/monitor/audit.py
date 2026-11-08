"""Draw a reproducible random sample for checking records by hand against TED."""
from __future__ import annotations

import csv
import random
from pathlib import Path

from .store import read_rows

ROOT = Path(__file__).resolve().parents[2]
SIZE = 20
SEED = 2026


def main() -> None:
    target = ROOT / "docs" / "manual_check.csv"
    if target.exists():
        raise SystemExit(f"{target} already exists; delete it to draw a new sample")
    rows = read_rows(ROOT / "data" / "notices.csv")
    sample = random.Random(SEED).sample(rows, min(SIZE, len(rows)))
    columns = ["publication_number", "publication_date", "buyer_country", "buyer_name",
               "winner_names", "total_value", "total_value_currency", "source_url"]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns + ["matches_source", "note"])
        for row in sample:
            writer.writerow([row[c] for c in columns] + ["", ""])
    print(f"Wrote {len(sample)} records to {target}. Fill in matches_source with yes or no.")


if __name__ == "__main__":
    main()
