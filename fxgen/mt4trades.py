"""Direct MT4 clients' trades in mt4.MT4_TRADES.

  python -m fxgen.mt4trades open --login 1000 --symbol EURUSD.retail --side buy --lots 1 --time "2026-10-27 09:00:00"

open sends the trade through the bridge simulation (order MT4, XCore order
and legs, as fxgen.orders does) and, if it fills, writes the MT4 ticket.
While a ticket is open, CLOSE_PRICE, CONV_RATE2 and PROFIT show the price it
would close at now. Rules are in docs/domain-notes.md, "MT4 trades" and "MT4
trade behaviour: direct clients".
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from fxgen.db import connect
from fxgen.orders import FIRST_TICKET, HALF_SPREAD_POINTS, MIDS, TRADABLE_SQL, dec, execute, lot_contracts, mt4_fill, save

CURRENCY_DECIMALS = {"JPY": 0}   # deposit currency rounding; 2 otherwise
OPEN_DATE = "1970-01-01 00:00:00"


def money(amount: Decimal, currency: str) -> Decimal:
    return amount.quantize(Decimal(1).scaleb(-CURRENCY_DECIMALS.get(currency, 2)), rounding=ROUND_HALF_UP)


def rate(base: str, deposit: str, quote: str, price: Decimal) -> Decimal:
    """CONV_RATE (Josh's definition): base currency -> deposit currency.

    When the deposit currency is the quote currency the trade's own price is
    the rate, so quote -> deposit (rate / price) is exactly 1.
    """
    if base == deposit:
        return Decimal(1)
    if quote == deposit:
        return price
    for a, b, inverse in ((base, deposit, False), (deposit, base, True)):
        if f"{a}/{b}" in MIDS:
            mid = Decimal(MIDS[f"{a}/{b}"])
            return 1 / mid if inverse else mid
    return rate(base, "USD", "", Decimal(0)) * rate("USD", deposit, "", Decimal(0))


def close_quote(row: dict, side: str, mid: Decimal) -> Decimal:
    """The MT4 price a ticket on `side` would close at now: the opposite side
    of the book, with XCore and close-side group markup, rounded for the broker."""
    point = Decimal(1).scaleb(-int(row["DIGITS"]))
    half = HALF_SPREAD_POINTS.get(row["XCORE_SYMBOL"], 3)
    gm = row["SPREAD_DIFF"] // 2
    if side == "buy":   # closes by selling at the bid
        return (mid - half * point + row["MARKUP_BID"] - gm * point).quantize(point, rounding=ROUND_FLOOR)
    return (mid + half * point + row["MARKUP_ASK"] + gm * point).quantize(point, rounding=ROUND_CEILING)


def profit(side: str, contracts: Decimal, open_price: Decimal, close_price: Decimal,
           conv_rate2: Decimal, currency: str) -> Decimal:
    """P/L in deposit currency: quote-currency P/L x (CONV_RATE2 / close price)."""
    sign = 1 if side == "buy" else -1
    return money(sign * (close_price - open_price) * contracts * conv_rate2 / close_price, currency)


def open_trade(cur, login: int, symbol: str, side: str, lots: str, when: datetime, rng: random.Random) -> str:
    cur.execute(TRADABLE_SQL + " WHERE mt4.LOGIN = %s AND mt4.SYMBOL = %s", (login, symbol))
    cols = [c[0] for c in cur.description]
    row = dict(zip(cols, cur.fetchall()[0]))
    cur.execute("SELECT CURRENCY, CONTRACT_SIZE FROM mt4.MT4_SYMBOLS WHERE SERVER = 'trade/mt4' AND SYMBOL = %s",
                (symbol,))
    base, contract_size = cur.fetchone()
    deposit = row["ACCOUNT_CURRENCY"]
    quote = row["XCORE_SYMBOL"].split("/")[1] if "/" in row["XCORE_SYMBOL"] else "USD"
    cur.execute("SELECT GREATEST(COALESCE((SELECT MAX(TICKET) FROM xcore.XCORE_ORDER_MT4), 0),"
                " COALESCE((SELECT MAX(TICKET) FROM mt4.MT4_TRADES), 0))")
    ticket = max(cur.fetchone()[0] + 1, FIRST_TICKET)

    point = Decimal(1).scaleb(-int(row["DIGITS"]))
    mid = (Decimal(MIDS[row["XCORE_SYMBOL"]]) * dec(1 + rng.gauss(0, 0.0005))).quantize(point)
    open_ms = int(when.replace(tzinfo=timezone.utc).timestamp() * 1000)
    ex = execute(row, side, lot_contracts(row, lots), False, open_ms, mid, rng, None)
    _, size, fill_ms = save(cur, row, ex, ticket, False)
    if not size:
        return f"{side} {lots} {symbol} for {login}: rejected, no ticket"
    _, open_price = mt4_fill(row, ex, False)

    volume = int(size / lot_contracts(row, "0.01"))          # 100 = 1 lot
    conv1 = rate(base, deposit, quote, open_price)
    commission = money(-Decimal(row["COMM_BASE"]) * volume / 100 * dec(contract_size) * conv1 / 100_000, deposit)
    close_price = close_quote(row, side, mid)
    conv2 = rate(base, deposit, quote, close_price)
    pl = profit(side, size, open_price, close_price, conv2, deposit)
    open_time = datetime.fromtimestamp(fill_ms // 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO mt4.MT4_TRADES (SERVER, TICKET, LOGIN, SYMBOL, DIGITS, CMD, VOLUME, OPEN_TIME, OPEN_PRICE, "
        "CLOSE_TIME, CLOSE_PRICE, CONV_RATE1, CONV_RATE2, COMMISSION, COMMISSION_AGENT, SWAPS, PROFIT, COMMENT) "
        "VALUES ('trade/mt4', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, %s, '')",
        (ticket, login, symbol, row["DIGITS"], 0 if side == "buy" else 1, volume, open_time, open_price,
         OPEN_DATE, close_price, conv1, conv2, commission, pl))
    return (f"ticket {ticket}: {login} {side} {volume / 100:g} lots {symbol} at {open_price}, opened {open_time}, "
            f"commission {commission}, floating P/L {pl}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("open", help="open a ticket for a direct MT4 client")
    p.add_argument("--login", type=int, required=True)
    p.add_argument("--symbol", required=True, help="MT4 symbol, e.g. EURUSD.retail")
    p.add_argument("--side", choices=("buy", "sell"), required=True)
    p.add_argument("--lots", required=True)
    p.add_argument("--time", type=datetime.fromisoformat, required=True, help="GMT request time")
    p.add_argument("--seed", type=int)
    args = parser.parse_args()

    conn = connect()
    cur = conn.cursor()
    print(open_trade(cur, args.login, args.symbol, args.side, args.lots, args.time, random.Random(args.seed)))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
