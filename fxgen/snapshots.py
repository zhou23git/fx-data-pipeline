"""Open-position snapshots around end of day (reporting.eod_snapshots).

Equiti allowed no trading from 16:58 to 17:02 New York. In that window Josh
copied every open ticket at 16:59:55, before the day's swap is charged, and
again at 17:00:05, right after. The end-of-day run writes both: after the
open tickets are marked to the price snapshot, then after charge_swaps.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fxgen.mt4trades import OPEN_DATE

BEFORE_SWAPS = timedelta(seconds=-4)   # 16:59:55 New York, from end of day at 16:59:59
AFTER_SWAPS = timedelta(seconds=6)     # 17:00:05 New York

COLUMNS = ("SERVER, TICKET, LOGIN, SYMBOL, CMD, VOLUME, OPEN_TIME, OPEN_PRICE, CLOSE_TIME, CLOSE_PRICE, "
           "CONV_RATE1, CONV_RATE2, COMMISSION, COMMISSION_AGENT, SWAPS, PROFIT, COMMENT")


def snapshot_open(cur, day: date, when: datetime) -> str:
    """Copy every open buy and sell ticket into reporting.eod_snapshots,
    stamped with trading day `day` and GMT time `when`. A rerun replaces
    that snapshot."""
    stamp = when.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("DELETE FROM reporting.eod_snapshots WHERE SnapTime = %s", (stamp,))
    cur.execute(f"INSERT INTO reporting.eod_snapshots (SnapDate, SnapTime, {COLUMNS}) "
                f"SELECT %s, %s, {COLUMNS} FROM mt4.MT4_TRADES "
                "WHERE SERVER = 'trade/mt4' AND CMD IN (0, 1) AND CLOSE_TIME = %s AND OPEN_TIME <= %s",
                (day, stamp, OPEN_DATE, stamp))
    return f"{cur.rowcount} open tickets at {stamp} GMT"
