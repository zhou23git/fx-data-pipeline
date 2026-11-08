"""The daily run: simulate every hour since the last run, up to 17:00 New York.

  python -m fxgen.daily [--dry-run] [--log logs/daily.log]

Scheduled at 16:55 New York time, Josh's last hourly run of the day. It
picks up from the hour after the last simulated event and runs fxgen.hourly for each hour up to today's 17:00 New
York close, so it simulates the rest of the trading day "into the future",
including end of day at 16:59:59 (swap rates, price snapshot, swaps,
statements), which really runs just after the close.
A missed day is caught up on the next run.

The FX market is closed from Friday 17:00 to Sunday 17:00 New York time.
Those hours don't trade, but end of day on Saturday and Sunday still writes statements
(fxgen.hourly.closed_hour). A rerun over a weekend rewrites the same files.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fxgen.db import connect
from fxgen.hourly import CLOSE_HOUR, closed_hour, market_open, run_hour
from fxgen.prices import eod_of, is_snapshot_run

NEW_YORK, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")
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
        if market_open(hour) or is_snapshot_run(eod_of(hour)):
            hours.append(hour)
        hour += timedelta(hours=1)
    print(f"[{datetime.now(UTC):%Y-%m-%d %H:%M:%S} GMT] daily run: {start:%Y-%m-%d %H:00} to {end:%Y-%m-%d %H:00} GMT, "
          f"{sum(map(market_open, hours))} market hours, {sum(not market_open(h) for h in hours)} closed-day statement runs")
    if args.dry_run or not hours:
        conn.close()
        return
    rng = random.Random(int(hours[0].replace(tzinfo=UTC).timestamp()))
    for hour in hours:
        log = run_hour(cur, hour, rng) if market_open(hour) else closed_hour(cur, hour)
        conn.commit()
        print(f"{log[0]}  {log[-1]}")
    print(f"[{datetime.now(UTC):%Y-%m-%d %H:%M:%S} GMT] done")
    conn.close()


if __name__ == "__main__":
    main()
