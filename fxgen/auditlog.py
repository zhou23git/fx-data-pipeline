"""xcore.XCORE_CONFIG_AUDIT_LOG, shared by the config-change programs.

LOG_TIME never goes backwards, so LOG_ID order is time order.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone


def change_time(when: datetime | None) -> datetime:
    """The given GMT time, or now, cut to the milliseconds LOG_TIME keeps."""
    when = when or datetime.now(timezone.utc).replace(tzinfo=None)
    return when.replace(microsecond=when.microsecond // 1000 * 1000)


def latest(cur) -> tuple[int, datetime] | tuple[None, None]:
    cur.execute("SELECT LOG_ID, LOG_TIME FROM xcore.XCORE_CONFIG_AUDIT_LOG ORDER BY LOG_ID DESC LIMIT 1")
    row = cur.fetchone()
    return (row[0], row[1]) if row else (None, None)


def check_order(cur, when: datetime) -> None:
    _, last = latest(cur)
    if last is not None and when < last:
        sys.exit(f"Change time {when} is before the latest log entry ({last}); the log must stay in time order.")


def write(cur, when: datetime, message: str) -> None:
    cur.execute("INSERT INTO xcore.XCORE_CONFIG_AUDIT_LOG (LOG_TIME, MESSAGE) VALUES (%s, %s)", (when, message))
