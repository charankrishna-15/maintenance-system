"""Small time helpers. All timestamps are stored in UTC as ISO-8601 strings
(e.g. 2026-10-10T13:05:00Z). The format sorts correctly as plain text and the
browser can parse it directly."""

from datetime import datetime, timedelta, timezone

FMT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(FMT)


def now_iso() -> str:
    return to_iso(utcnow())


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, FMT).replace(tzinfo=timezone.utc)


def add_hours_iso(value: str, hours: float) -> str:
    return to_iso(parse_iso(value) + timedelta(hours=hours))


def hours_between(start: str, end: str) -> float:
    return (parse_iso(end) - parse_iso(start)).total_seconds() / 3600.0
