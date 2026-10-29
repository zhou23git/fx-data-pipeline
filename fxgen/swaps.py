"""Daily swap rates in mt4.MT4_SYMBOLS, as the swap plugin loads them.

  python -m fxgen.swaps rates --seed 1

For every symbol with SWAP_ENABLE = 1, draws a 1-5 point differential and
writes it as a price delta: buys pay (SWAP_LONG = -n x POINT) and sells get
paid (SWAP_SHORT = +n x POINT). EURUSD at 3 points: -0.00003 / +0.00003, so a
1M position is -30 / +30 a day. The plain, .retail and .b2b versions of a
pair share one draw. Symbols with swaps disabled are left alone.

At end of day every open buy or sell ticket on a swap-enabled symbol gets one
day's swap added to SWAPS: contracts x SWAP_LONG (buys) or SWAP_SHORT
(sells), a quote-currency amount converted to the deposit currency at the
end-of-day price, as PROFIT is. The hourly process does both on its 16:55 New
York run, after that hour's trades: rates first, then the price snapshot,
then the charge.

  python -m fxgen.swaps charge --time "2026-10-28 20:55:00"
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime
from decimal import Decimal

from fxgen.db import connect
from fxgen.mt4trades import OPEN_DATE, money, rate

SWAP_POINTS = (1, 5)


def set_swaps(cur, rng: random.Random) -> list[str]:
    cur.execute("SELECT s.SYMBOL, r.XCORE_SYMBOL, s.DIGITS FROM mt4.MT4_SYMBOLS s "
                "JOIN reference.mt4_symbol_reference r ON r.MT4_SYMBOL = s.SYMBOL "
                "WHERE s.SERVER = 'trade/mt4' AND s.SWAP_ENABLE = 1 ORDER BY s.SYMBOL")
    draws, log = {}, []
    for symbol, xcore, digits in cur.fetchall():
        n = draws.setdefault(xcore, rng.randint(*SWAP_POINTS))
        delta = (n * Decimal(1).scaleb(-int(digits)))
        cur.execute("UPDATE mt4.MT4_SYMBOLS SET SWAP_LONG = %s, SWAP_SHORT = %s "
                    "WHERE SERVER = 'trade/mt4' AND SYMBOL = %s", (-delta, delta, symbol))
        log.append(f"{symbol} long {-delta} / short {delta}")
    return log


OPEN_SWAP_SQL = """
SELECT t.TICKET, t.CMD, t.VOLUME, s.CONTRACT_SIZE, s.SWAP_LONG, s.SWAP_SHORT, s.CURRENCY AS BASE,
       u.CURRENCY AS DEPOSIT, r.XCORE_SYMBOL, (p.BID + p.ASK) / 2 AS MID
FROM mt4.MT4_TRADES t
JOIN mt4.MT4_SYMBOLS s ON s.SERVER = t.SERVER AND s.SYMBOL = t.SYMBOL
JOIN mt4.MT4_USERS u ON u.SERVER = t.SERVER AND u.LOGIN = t.LOGIN
JOIN mt4.MT4_PRICES p ON p.SERVER = t.SERVER AND p.SYMBOL = t.SYMBOL
JOIN reference.mt4_symbol_reference r ON r.MT4_SYMBOL = t.SYMBOL
WHERE t.SERVER = 'trade/mt4' AND t.CMD IN (0, 1) AND t.CLOSE_TIME = %s AND t.OPEN_TIME <= %s
  AND s.SWAP_ENABLE = 1
ORDER BY t.TICKET
"""


def charge_swaps(cur, when: datetime) -> list[str]:
    """Add one day's swap to every open ticket opened by `when`."""
    cur.execute(OPEN_SWAP_SQL, (OPEN_DATE, when.strftime("%Y-%m-%d %H:%M:%S")))
    cols = [c[0] for c in cur.description]
    log = []
    for t in [dict(zip(cols, r)) for r in cur.fetchall()]:
        mid = Decimal(str(t["MID"]))
        quote = t["XCORE_SYMBOL"].split("/")[1]
        delta = Decimal(str(t["SWAP_LONG"] if t["CMD"] == 0 else t["SWAP_SHORT"]))
        contracts = Decimal(t["VOLUME"]) / 100 * Decimal(str(t["CONTRACT_SIZE"]))
        amount = money(contracts * delta * rate(t["BASE"], t["DEPOSIT"], quote, mid) / mid, t["DEPOSIT"])
        cur.execute("UPDATE mt4.MT4_TRADES SET SWAPS = SWAPS + %s WHERE SERVER = 'trade/mt4' AND TICKET = %s",
                    (amount, t["TICKET"]))
        log.append(f"ticket {t['TICKET']}: swap {amount} {t['DEPOSIT']}")
    return log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", nargs="?", choices=("rates", "charge"), default="rates")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--time", type=datetime.fromisoformat, help="GMT end-of-day time, for charge")
    args = parser.parse_args()
    conn = connect()
    cur = conn.cursor()
    if args.action == "rates":
        print(f"{len(set_swaps(cur, random.Random(args.seed)))} symbols' swaps set")
    else:
        if args.time is None:
            parser.error("charge needs --time")
        log = charge_swaps(cur, args.time)
        print(f"{len(log)} open tickets charged swaps")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
