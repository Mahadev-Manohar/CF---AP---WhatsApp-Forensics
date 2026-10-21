"""Timestamp helpers. All times in WhatsApp artifacts are treated as UTC (see docs/deviations.md)."""

from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def from_ms(ms: int | float | None) -> datetime | None:
    """13-digit millisecond Unix epoch -> aware UTC datetime. -1/None/0 mean 'not set'."""
    if ms is None or ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def from_s(s: int | float | None) -> datetime | None:
    """10-digit Unix epoch seconds -> aware UTC datetime."""
    if s is None or s <= 0:
        return None
    return datetime.fromtimestamp(s, tz=UTC)


def to_ms(dt: datetime) -> int:
    return round(dt.timestamp() * 1000)


def iso(dt: datetime | None, ms: bool = True) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S" + (f".{dt.microsecond // 1000:03d}" if ms else "")) + " UTC"


def parse_log_ts(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC)
