"""Turn raw TED notices into validated rows.

Rows that break a rule go to quarantine with the reason attached. They are never
silently dropped or repaired. Missing information stays empty and is never estimated.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, ValidationError, field_validator

from .ted import DEFENCE_CPV

COLUMNS = [
    "publication_number", "publication_date", "form_type", "notice_type",
    "procedure_type", "title", "buyer_name", "buyer_country", "cpv_codes",
    "cpv_group", "winner_names", "total_value", "total_value_currency",
    "value_disclosed", "winner_disclosed", "source_url", "first_retrieved_at",
    "last_retrieved_at",
]


class Notice(BaseModel):
    publication_number: str
    publication_date: date
    form_type: str
    notice_type: str
    procedure_type: str
    title: str
    buyer_name: str
    buyer_country: str
    cpv_codes: str
    cpv_group: str
    winner_names: str
    total_value: float | None
    total_value_currency: str
    value_disclosed: bool
    winner_disclosed: bool
    source_url: str

    @field_validator("publication_number")
    @classmethod
    def valid_number(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9]\d*-\d{4}", value):
            raise ValueError("publication number is not of the form 123456-2026")
        return value

    @field_validator("publication_date")
    @classmethod
    def plausible_date(cls, value: date) -> date:
        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
        if not date(2010, 1, 1) <= value <= tomorrow:
            raise ValueError("publication date outside 2010 to today")
        return value

    @field_validator("buyer_country")
    @classmethod
    def valid_country(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z]{3}(;[A-Z]{3})*", value):
            raise ValueError("buyer country is not ISO alpha-3")
        return value

    @field_validator("total_value")
    @classmethod
    def non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("negative contract value")
        return value

    @field_validator("cpv_group")
    @classmethod
    def known_group(cls, value: str) -> str:
        if value not in DEFENCE_CPV.values():
            raise ValueError("no defence CPV code on the notice")
        return value


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _unique(values) -> list[str]:
    return list(dict.fromkeys(str(v).strip() for v in values if str(v).strip()))


def _text(value) -> str:
    """Read a plain or language-keyed field, preferring English."""
    if isinstance(value, dict):
        lower = {k.lower(): v for k, v in value.items()}
        key = "eng" if "eng" in lower else (sorted(lower)[0] if lower else None)
        value = lower.get(key) if key else None
    return "; ".join(_unique(_as_list(value)))


def _value(raw) -> float | None:
    """Keep a value only if the notice states exactly one distinct amount."""
    amounts = _unique(_as_list(raw))
    return float(amounts[0]) if len(amounts) == 1 else None


def to_row(raw: dict) -> dict:
    """Raises ValueError, TypeError or ValidationError if the notice is unusable."""
    number = str(raw.get("publication-number", "")).strip().lstrip("0")
    cpv = _unique(_as_list(raw.get("classification-cpv")))
    group = next((DEFENCE_CPV[c[:3]] for c in cpv if c[:3] in DEFENCE_CPV), "")
    value = _value(raw.get("total-value"))
    currencies = _unique(_as_list(raw.get("total-value-cur")))
    winners = _text(raw.get("winner-name"))
    notice = Notice(
        publication_number=number,
        publication_date=str(raw.get("publication-date", ""))[:10],
        form_type=_text(raw.get("form-type")),
        notice_type=_text(raw.get("notice-type")),
        procedure_type=_text(raw.get("procedure-type")),
        title=_text(raw.get("notice-title")),
        buyer_name=_text(raw.get("buyer-name")),
        buyer_country=";".join(_unique(_as_list(raw.get("buyer-country")))),
        cpv_codes=";".join(cpv),
        cpv_group=group,
        winner_names=winners,
        total_value=value,
        total_value_currency=currencies[0] if value is not None and len(currencies) == 1 else "",
        # TED notices sometimes state 0; that is treated as not disclosed.
        value_disclosed=bool(value and len(currencies) == 1),
        winner_disclosed=bool(winners),
        source_url=f"https://ted.europa.eu/en/notice/-/detail/{number}",
    )
    return notice.model_dump(mode="json")


def clean(raw_notices: list[dict]) -> tuple[list[dict], list[dict]]:
    rows, quarantine = [], []
    for raw in raw_notices:
        try:
            rows.append(to_row(raw))
        except (ValidationError, ValueError, TypeError) as error:
            reason = "; ".join(e["msg"] for e in error.errors()) if isinstance(error, ValidationError) else str(error)
            quarantine.append({"publication_number": str(raw.get("publication-number", "")), "reason": reason})
    return rows, quarantine
