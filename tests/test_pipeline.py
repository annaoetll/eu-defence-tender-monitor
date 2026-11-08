"""All test notices below are made up. They only imitate the shape of API responses."""
from datetime import date

import pytest

from monitor import pipeline
from monitor.clean import clean, to_row
from monitor.dashboard import render
from monitor.store import merge, read_rows
from monitor.ted import DEFENCE_CPV, build_query


def raw(**changes):
    notice = {
        "publication-number": "00123456-2026",
        "publication-date": "2026-10-01+02:00",
        "form-type": "result",
        "notice-type": "can-standard",
        "procedure-type": "open",
        "notice-title": {"deu": "Titel", "eng": "Title"},
        "buyer-name": {"deu": ["Testkäufer"]},
        "buyer-country": ["DEU"],
        "classification-cpv": ["35300000", "35300000"],
        "winner-name": {"eng": ["Firm A", "Firm B", "Firm A"]},
        "total-value": 1000.5,
        "total-value-cur": "EUR",
    }
    notice.update(changes)
    return notice


def test_query_covers_all_groups():
    query = build_query(date(2026, 1, 1), date(2026, 1, 31))
    assert all(f"{group}00000" in query for group in DEFENCE_CPV)
    assert "publication-date>=20260101" in query and "publication-date<=20260131" in query


def test_normalises_a_notice():
    row = to_row(raw())
    assert row["publication_number"] == "123456-2026"
    assert row["publication_date"] == "2026-10-01"
    assert row["title"] == "Title"
    assert row["buyer_name"] == "Testkäufer"
    assert row["winner_names"] == "Firm A; Firm B"
    assert row["cpv_group"] == "Weapons and ammunition"
    assert row["value_disclosed"] and row["winner_disclosed"]
    assert row["source_url"].endswith("/123456-2026")


@pytest.mark.parametrize(
    "value,currency",
    [(0, "EUR"), (None, None), ([100, 200], "EUR"), (100, ["EUR", "PLN"])],
)
def test_ambiguous_or_zero_value_is_not_disclosed(value, currency):
    row = to_row(raw(**{"total-value": value, "total-value-cur": currency}))
    assert not row["value_disclosed"]


def test_missing_winner_stays_empty():
    row = to_row(raw(**{"winner-name": None}))
    assert row["winner_names"] == "" and not row["winner_disclosed"]


@pytest.mark.parametrize(
    "bad",
    [
        {"publication-number": "abc"},
        {"publication-date": "2099-01-01"},
        {"publication-date": ""},
        {"buyer-country": ["DE"]},
        {"buyer-country": None},
        {"classification-cpv": ["35100000"]},
        {"total-value": -5},
        {"total-value": "unknown"},
    ],
)
def test_bad_notice_goes_to_quarantine(bad):
    rows, quarantine = clean([raw(**bad)])
    assert not rows and len(quarantine) == 1 and quarantine[0]["reason"]


def test_merge_is_idempotent_and_tracks_changes():
    row = to_row(raw())
    first, added, changed = merge([], [row], "t1")
    assert (added, changed) == (1, 0)
    second, added, changed = merge(first, [row], "t2")
    assert (len(second), added, changed) == (1, 0, 0)
    assert second[0]["first_retrieved_at"] == "t1" and second[0]["last_retrieved_at"] == "t2"
    edited = to_row(raw(**{"total-value": 2000}))
    _, added, changed = merge(second, [edited], "t3")
    assert (added, changed) == (0, 1)


def test_csv_round_trip_does_not_report_false_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_notices", lambda s, u: ([raw()], 1))
    for _ in range(2):
        log = pipeline.run(7, tmp_path / "data", tmp_path / "site")
    assert (log["added"], log["changed"], log["total_in_dataset"]) == (0, 0, 1)
    assert (tmp_path / "site" / "index.html").exists() and (tmp_path / "site" / "notices.csv").exists()


def test_incomplete_download_leaves_files_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_notices", lambda s, u: ([raw()], 2))
    with pytest.raises(pipeline.TedError):
        pipeline.run(7, tmp_path / "data", tmp_path / "site")
    assert not (tmp_path / "data" / "notices.csv").exists()


def test_mostly_invalid_download_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_notices", lambda s, u: ([raw(), raw(**{"buyer-country": "x"})], 2))
    with pytest.raises(pipeline.TedError):
        pipeline.run(7, tmp_path / "data", tmp_path / "site")


def test_page_escapes_source_text(tmp_path):
    row = to_row(raw(**{"buyer-name": {"eng": ["<script>alert(1)</script>"]}}))
    merged, _, _ = merge([], [row], "t")
    page = render(merged, {}, "check")
    assert "<script>alert(1)" not in page and "&lt;script&gt;" in page


def test_page_renders_without_data():
    assert "EU Defence Tender Monitor" in render([], {}, "check")
