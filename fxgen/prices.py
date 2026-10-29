"""End-of-day price snapshot in mt4.MT4_PRICES.

  python -m fxgen.prices --time "2026-10-28 20:55:00" --seed 1

Writes a fake bid and ask for every MT4 symbol, overwriting the previous
snapshot. The plain, .retail and .b2b versions of a pair share one quote,
since they are the same market. The hourly process calls this on its 16:55
New York run; Josh read the table at 16:59:59 New York time for end of day.
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fxgen.db import connect
from fxgen.orders import HALF_SPREAD_POINTS, MIDS, dec

NEW_YORK = ZoneInfo("America/New_York")
SNAPSHOT_NY = (16, 55)   # New York time of the run that writes the snapshot


def is_snapshot_run(when: datetime) -> bool:
    """Whether a GMT run time is 16:55 in New York (EDT or EST)."""
    ny = when.replace(tzinfo=ZoneInfo("UTC")).astimezone(NEW_YORK)
    return (ny.hour, ny.minute) == SNAPSHOT_NY


def snapshot_prices(cur, when: datetime, rng: random.Random) -> list[str]:
    cur.execute("SELECT MT4_SYMBOL, XCORE_SYMBOL, DIGITS FROM reference.mt4_symbol_reference ORDER BY MT4_SYMBOL")
    mids, log, done = {}, [], when.strftime("%Y-%m-%d %H:%M:%S")
    for symbol, xcore, digits in cur.fetchall():
        point = Decimal(1).scaleb(-int(digits))
        if xcore not in mids:
            mids[xcore] = Decimal(MIDS[xcore]) * dec(1 + rng.gauss(0, 0.0005))
        half = HALF_SPREAD_POINTS.get(xcore, 3) * point
        bid, ask = (mids[xcore] - half).quantize(point), (mids[xcore] + half).quantize(point)
        cur.execute("REPLACE INTO mt4.MT4_PRICES (SERVER, SYMBOL, BID, ASK, MODIFY_TIME) "
                    "VALUES ('trade/mt4', %s, %s, %s, %s)", (symbol, bid, ask, done))
        log.append(f"{symbol} {bid} / {ask}")
    return log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--time", type=datetime.fromisoformat, required=True, help="GMT time of the snapshot")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    conn = connect()
    cur = conn.cursor()
    log = snapshot_prices(cur, args.time, random.Random(args.seed))
    conn.commit()
    print(f"{len(log)} prices at {args.time:%Y-%m-%d %H:%M:%S} GMT")
    conn.close()


if __name__ == "__main__":
    main()
