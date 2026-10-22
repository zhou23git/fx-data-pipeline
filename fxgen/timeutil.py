"""Clock conventions shared by every simulated system.

MT4 and XCore both record GMT: MT4 in whole seconds, XCore with milliseconds.
End of day follows the New York close, so in GMT it moves with US daylight
saving. The trading day and market hours come from Josh's GMT EOD reference
file, not from a rule in this module.
"""
from __future__ import annotations

from datetime import date, datetime

MT4_EPOCH = "1970-01-01 00:00:00"


def server_date(utc: datetime) -> date:
    """Trading day a GMT time belongs to."""
    raise NotImplementedError("Trading day comes from the GMT EOD reference file, which isn't loaded yet.")


def is_market_open(utc: datetime) -> bool:
    raise NotImplementedError("Market hours come from the GMT EOD reference file, which isn't loaded yet.")


def fmt_mt4(utc: datetime) -> str:
    """MT4 MySQL export format: GMT, whole seconds."""
    return utc.strftime("%Y-%m-%d %H:%M:%S")


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
