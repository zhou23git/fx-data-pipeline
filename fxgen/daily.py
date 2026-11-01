"""The daily run: simulate every hour since the last run, up to 17:00 New York.

  python -m fxgen.daily [--dry-run] [--log logs/daily.log]

Scheduled at 16:30 New York time. It picks up from the hour after the last
simulated event and runs fxgen.hourly for each hour up to today's 17:00 New
York close, so it simulates the rest of the trading day "into the future",
including the 16:55 end-of-day run (swap rates, price snapshot, swaps).
A missed day is caught up on the next run.

The FX market is closed from Friday 17:00 to Sunday 17:00 New York time;
those hours are skipped.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fxgen.db import connect
from fxgen.hourly import run_hour

NEW_YORK, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")
CLOSE_HOUR = 17   # New York trading day ends (and the week opens on Sunday) at 17:00


def market_open(hour: datetime) -> bool:
    """Whether the GMT hour starting at `hour` is inside the FX trading week."""
    ny = hour.replace(tzinfo=UTC).astimezone(NEW_YORK)
    if ny.weekday() == 4:                        # Friday: open until 17:00
        return ny.hour < CLOSE_HOUR
    if ny.weekday() == 5:                        # Saturday
        return False
    if ny.weekday() == 6:                        # Sunday: open from 17:00
        return ny.hour >= CLOSE_HOUR
    return True


def next_hour(cur) -> datetime:
    """The GMT hour after the last simulated event."""
    cur.execute("SELECT MAX(GREATEST(OPEN_TIME, CLOSE_TIME)) FROM mt4.MT4_TRADES WHERE SERVER = 'trade/mt4'")
    (last,) = cur.fetchone()
    if last is None:
        sys.exit("MT4_TRADES is empty; seed a first day with fxgen.hourly --start.")
    return last.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def close_today(now: datetime | None = None) -> datetime:
    """Today's 17:00 New York close, as naive GMT."""
    ny = (now or datetime.now(UTC)).astimezone(NEW_YORK)
    close = ny.replace(hour=CLOSE_HOUR, minute=0, second=0, microsecond=0)
    return close.astimezone(UTC).replace(tzinfo=None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="show the hours it would run, change nothing")
    parser.add_argument("--log", help="append output to this file (for scheduled runs)")
    args = parser.parse_args()
    if args.log:
        sys.stdout = sys.stderr = open(args.log, "a", encoding="utf-8", buffering=1)

    conn = connect()
    cur = conn.cursor()
    start, end = next_hour(cur), close_today()
    hours = []
    hour = start
    while hour < end:
        if market_open(hour):
            hours.append(hour)
        hour += timedelta(hours=1)
    print(f"[{datetime.now(UTC):%Y-%m-%d %H:%M:%S} GMT] daily run: {start:%Y-%m-%d %H:00} to {end:%Y-%m-%d %H:00} GMT, "
          f"{len(hours)} market hours")
    if args.dry_run or not hours:
        conn.close()
        return
    rng = random.Random(int(hours[0].replace(tzinfo=UTC).timestamp()))
    for hour in hours:
        log = run_hour(cur, hour, rng)
        conn.commit()
        print(f"{log[0]}  {log[-1]}")
    print(f"[{datetime.now(UTC):%Y-%m-%d %H:%M:%S} GMT] done")
    conn.close()


if __name__ == "__main__":
    main()
