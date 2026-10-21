"""Clock conventions shared by every simulated system.

MT4 servers run on "New York close" time: midnight on the server is 17:00 in
New York, which makes the server GMT+3 while the US is on daylight saving and
GMT+2 otherwise. XCore records UTC with milliseconds. Keeping both conventions
is deliberate -- lining them up is part of the exercise.

US DST is computed by rule rather than with zoneinfo so the generator runs on
Windows Python, which ships without a time zone database.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

MT4_EPOCH = "1970-01-01 00:00:00"


def _nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    first_sunday = first + timedelta(days=(6 - first.weekday()) % 7)
    return first_sunday + timedelta(weeks=n - 1)


def server_offset(utc: datetime) -> timedelta:
    # US DST: second Sunday of March 02:00 EST (07:00 UTC) to first Sunday of
    # November 02:00 EDT (06:00 UTC).
    dst_start = datetime.combine(_nth_sunday(utc.year, 3, 2), time(7))
    dst_end = datetime.combine(_nth_sunday(utc.year, 11, 1), time(6))
    return timedelta(hours=3 if dst_start <= utc < dst_end else 2)


def to_server(utc: datetime) -> datetime:
    return utc + server_offset(utc)


def server_date(utc: datetime) -> date:
    return to_server(utc).date()


def is_market_open(utc: datetime) -> bool:
    """FX trades Monday 00:00 to Friday 23:59 server time."""
    return to_server(utc).weekday() < 5


def fmt_mt4(utc: datetime) -> str:
    """MT4 MySQL export format: server time, whole seconds."""
    return to_server(utc).strftime("%Y-%m-%d %H:%M:%S")


def fmt_utc_ms(utc: datetime) -> str:
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def unix(utc: datetime) -> int:
    return int((utc - datetime(1970, 1, 1)).total_seconds())


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def session(utc: datetime) -> str:
    """Trading session label XCore stamps on each order."""
    h = utc.hour
    if 21 <= h < 22:
        return "ROLLOVER"
    if h >= 22 or h < 7:
        return "ASIA"
    if h < 12:
        return "LONDON"
    if h < 16:
        return "LONDON_NY"
    return "NY"
