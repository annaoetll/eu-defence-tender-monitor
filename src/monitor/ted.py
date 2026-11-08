"""Fetch notices from the public TED Search API (no key required)."""
from __future__ import annotations

import time
from datetime import date

import requests

API_URL = "https://api.ted.europa.eu/v3/notices/search"

# CPV 2008 groups that are explicitly military. CPV matching is hierarchical,
# so each group also matches its sub-codes. Division 35 as a whole is avoided
# because it also contains police, fire-fighting and civil security equipment.
DEFENCE_CPV = {
    "353": "Weapons and ammunition",
    "354": "Military vehicles",
    "355": "Warships",
    "356": "Military aircraft and missiles",
    "357": "Military electronics",
    "358": "Individual and support equipment",
}

FIELDS = [
    "publication-number",
    "publication-date",
    "form-type",
    "notice-type",
    "procedure-type",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "winner-name",
    "total-value",
    "total-value-cur",
]


class TedError(RuntimeError):
    """The API did not return a complete, trustworthy result."""


def build_query(since: date, until: date) -> str:
    cpv = " ".join(f"{group}00000" for group in DEFENCE_CPV)
    return (
        f"classification-cpv IN ({cpv}) "
        f"AND publication-date>={since:%Y%m%d} "
        f"AND publication-date<={until:%Y%m%d}"
    )


def _post(session: requests.Session, body: dict, retries: int = 4) -> dict:
    for attempt in range(retries + 1):
        response = session.post(API_URL, json=body, timeout=60)
        if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            time.sleep(2**attempt)
            continue
        if response.status_code != 200:
            raise TedError(f"HTTP {response.status_code}: {response.text[:500]}")
        payload = response.json()
        if payload.get("timedOut"):  # A timed-out search can still return HTTP 200.
            raise TedError("TED reported timedOut=true")
        return payload
    raise TedError("Retries exhausted")


def fetch_notices(since: date, until: date) -> tuple[list[dict], int | None]:
    """Return all matching notices and the total count TED reports."""
    body = {
        "query": build_query(since, until),
        "fields": FIELDS,
        "limit": 250,
        "scope": "ALL",
        "paginationMode": "ITERATION",
        "onlyLatestVersions": False,
    }
    notices: list[dict] = []
    total = None
    with requests.Session() as session:
        session.headers["User-Agent"] = "eu-defence-tender-monitor (open-source portfolio project)"
        while True:
            page = _post(session, body)
            total = page.get("totalNoticeCount", total)
            batch = page.get("notices") or []
            if not batch:  # An empty page, not a missing token, marks the end.
                return notices, total
            notices.extend(batch)
            token = page.get("iterationNextToken")
            if not token:
                return notices, total
            body["iterationNextToken"] = token
            time.sleep(0.5)
