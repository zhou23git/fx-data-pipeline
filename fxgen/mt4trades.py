"""MT4 tickets in mt4.MT4_TRADES, for direct MT4 clients and API giveup logins.

  python -m fxgen.mt4trades open --login 1000 --symbol EURUSD.retail --side buy --lots 1 --time "2026-10-27 09:00:00"
  python -m fxgen.mt4trades hedge --tickets 1000010 1000013 --time "2026-10-27 16:00:00"
  python -m fxgen.mt4trades api --account uk_cov_100 --symbol EUR/USD --side sell --lots 3 --time "2026-10-27 17:00:00"
  python -m fxgen.mt4trades book --orders 21 22 23 24 25

open sends the trade through the bridge simulation (order MT4, XCore order
and legs, as fxgen.orders does) and, if it fills, writes the MT4 ticket.
While a ticket is open, CLOSE_PRICE and PROFIT show the price it would close
at now; CONV_RATE2 stays 0 until it closes. hedge closes open tickets
against each other. api places an API client's order and books it onto the
giveup login's tickets; book does that for orders already in XCore. Rules
are in docs/domain-notes.md, "MT4 trades" and the two "MT4 trade behaviour"
sections.
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from fxgen.db import connect
from fxgen.orders import (API_SQL, FIRST_TICKET, HALF_SPREAD_POINTS, MIDS, TRADABLE_SQL, dec, execute, lot_contracts,
                          mt4_fill, save, save_api)

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


def next_ticket(cur) -> int:
    cur.execute("SELECT GREATEST(COALESCE((SELECT MAX(TICKET) FROM xcore.XCORE_ORDER_MT4), 0),"
                " COALESCE((SELECT MAX(TICKET) FROM mt4.MT4_TRADES), 0))")
    return max(cur.fetchone()[0] + 1, FIRST_TICKET)


def open_trade(cur, login: int, symbol: str, side: str, lots: str, when: datetime, rng: random.Random) -> str:
    cur.execute(TRADABLE_SQL + " WHERE mt4.LOGIN = %s AND mt4.SYMBOL = %s", (login, symbol))
    cols = [c[0] for c in cur.description]
    row = dict(zip(cols, cur.fetchall()[0]))
    cur.execute("SELECT CURRENCY, CONTRACT_SIZE FROM mt4.MT4_SYMBOLS WHERE SERVER = 'trade/mt4' AND SYMBOL = %s",
                (symbol,))
    base, contract_size = cur.fetchone()
    deposit = row["ACCOUNT_CURRENCY"]
    quote = row["XCORE_SYMBOL"].split("/")[1] if "/" in row["XCORE_SYMBOL"] else "USD"
    ticket = next_ticket(cur)

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
         OPEN_DATE, close_price, conv1, 0, commission, pl))
    return (f"ticket {ticket}: {login} {side} {volume / 100:g} lots {symbol} at {open_price}, opened {open_time}, "
            f"commission {commission}, floating P/L {pl}")


TICKET_SQL = ("SELECT t.TICKET, t.LOGIN, t.SYMBOL, t.CMD, t.VOLUME, t.OPEN_TIME, t.OPEN_PRICE, t.CLOSE_TIME, "
              "t.CLOSE_PRICE, t.CONV_RATE1, t.CONV_RATE2, t.COMMISSION, t.COMMISSION_AGENT, t.SWAPS, t.DIGITS, "
              "u.CURRENCY AS DEPOSIT, s.CURRENCY AS BASE, s.CONTRACT_SIZE, r.XCORE_SYMBOL "
              "FROM mt4.MT4_TRADES t "
              "JOIN mt4.MT4_USERS u ON u.SERVER = t.SERVER AND u.LOGIN = t.LOGIN "
              "JOIN mt4.MT4_SYMBOLS s ON s.SERVER = t.SERVER AND s.SYMBOL = t.SYMBOL "
              "JOIN reference.mt4_symbol_reference r ON r.MT4_SYMBOL = t.SYMBOL "
              "WHERE t.SERVER = 'trade/mt4' AND t.TICKET = %s")


def load_ticket(cur, ticket: int) -> dict:
    cur.execute(TICKET_SQL, (ticket,))
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    if not rows:
        raise SystemExit(f"no ticket {ticket}")
    t = dict(zip(cols, rows[0]))
    for k in ("OPEN_PRICE", "CLOSE_PRICE", "CONV_RATE1", "CONV_RATE2", "COMMISSION", "COMMISSION_AGENT", "SWAPS"):
        t[k] = dec(t[k])
    t["QUOTE"] = t["XCORE_SYMBOL"].split("/")[1] if "/" in t["XCORE_SYMBOL"] else "USD"
    return t


def contracts(t: dict, volume: int) -> Decimal:
    return Decimal(volume) / 100 * dec(t["CONTRACT_SIZE"])


def partial_close(cur, t: dict, keep: int, comment: str) -> dict:
    """Split ticket t: it keeps `keep` volume and a child ticket opens for the
    rest, with the parent's open and the given comment. Commission, agent
    commission and swaps split by volume: the reduced ticket's share is
    rounded, the child gets the original minus it."""
    child_ticket = next_ticket(cur)
    rest = t["VOLUME"] - keep
    child = dict(t, TICKET=child_ticket, VOLUME=rest)
    for k in ("COMMISSION", "COMMISSION_AGENT", "SWAPS"):
        share = money(t[k] * keep / t["VOLUME"], t["DEPOSIT"])
        child[k] = t[k] - share
        t[k] = share
    t["VOLUME"] = keep
    side = "buy" if t["CMD"] == 0 else "sell"
    child_pl = profit(side, contracts(child, rest), child["OPEN_PRICE"], child["CLOSE_PRICE"],
                      rate(t["BASE"], t["DEPOSIT"], t["QUOTE"], child["CLOSE_PRICE"]), child["DEPOSIT"])
    cur.execute(
        "INSERT INTO mt4.MT4_TRADES (SERVER, TICKET, LOGIN, SYMBOL, DIGITS, CMD, VOLUME, OPEN_TIME, OPEN_PRICE, "
        "CLOSE_TIME, CLOSE_PRICE, CONV_RATE1, CONV_RATE2, COMMISSION, COMMISSION_AGENT, SWAPS, PROFIT, COMMENT) "
        "VALUES ('trade/mt4', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (child_ticket, t["LOGIN"], t["SYMBOL"], t["DIGITS"], t["CMD"], rest, t["OPEN_TIME"], child["OPEN_PRICE"],
         OPEN_DATE, child["CLOSE_PRICE"], child["CONV_RATE1"], 0, child["COMMISSION"],
         child["COMMISSION_AGENT"], child["SWAPS"], child_pl, comment))
    return child


def close_by_hedge(cur, tickets: list[int], when: datetime, rng: random.Random) -> list[str]:
    """Close the selected open tickets against each other (domain notes,
    "Close by hedge"). Nothing is sent to XCore. Close time and CONV_RATE2
    are set when the process completes (`when`), not from ticket 2."""
    ts = [load_ticket(cur, n) for n in tickets]
    if len({(t["LOGIN"], t["SYMBOL"]) for t in ts}) != 1:
        raise SystemExit("close by hedge needs tickets of one login and one symbol")
    if any(str(t["CLOSE_TIME"]) != OPEN_DATE or t["CMD"] not in (0, 1) for t in ts):
        raise SystemExit("close by hedge needs open buy and sell tickets")
    order = lambda t: (t["OPEN_TIME"], t["TICKET"])
    buys = sorted((t for t in ts if t["CMD"] == 0), key=order)
    sells = sorted((t for t in ts if t["CMD"] == 1), key=order)
    point = Decimal(1).scaleb(-int(ts[0]["DIGITS"]))
    market = (Decimal(MIDS[ts[0]["XCORE_SYMBOL"]]) * dec(1 + rng.gauss(0, 0.0005))).quantize(point)
    conv2 = rate(ts[0]["BASE"], ts[0]["DEPOSIT"], ts[0]["QUOTE"], market)
    done = when.strftime("%Y-%m-%d %H:%M:%S")
    log = []
    while buys and sells:
        main, other = sorted((buys[0], sells[0]), key=order)
        main_list, other_list = (buys, sells) if main is buys[0] else (sells, buys)
        main_list.pop(0)
        other_list.pop(0)
        if main["VOLUME"] != other["VOLUME"]:
            bigger, smaller, bigger_list = ((main, other, main_list) if main["VOLUME"] > other["VOLUME"]
                                            else (other, main, other_list))
            child = partial_close(cur, bigger, smaller["VOLUME"], f"from: {main['TICKET']}")
            bigger_list.insert(0, child)
            log.append(f"ticket {bigger['TICKET']} partially closed: {child['VOLUME'] / 100:g} lots to child "
                       f"{child['TICKET']}")
        # ticket 1 closes at ticket 2's open price and takes over its costs
        side = "buy" if main["CMD"] == 0 else "sell"
        close_price = other["OPEN_PRICE"]
        pl = profit(side, contracts(main, main["VOLUME"]), main["OPEN_PRICE"], close_price, conv2, main["DEPOSIT"])
        cur.execute(
            "UPDATE mt4.MT4_TRADES SET VOLUME = %s, CLOSE_TIME = %s, CLOSE_PRICE = %s, CONV_RATE2 = %s, "
            "COMMISSION = %s, COMMISSION_AGENT = %s, SWAPS = %s, PROFIT = %s "
            "WHERE SERVER = 'trade/mt4' AND TICKET = %s",
            (main["VOLUME"], done, close_price, conv2, main["COMMISSION"] + other["COMMISSION"],
             main["COMMISSION_AGENT"] + other["COMMISSION_AGENT"], main["SWAPS"] + other["SWAPS"], pl,
             main["TICKET"]))
        # ticket 2 is emptied
        cur.execute(
            "UPDATE mt4.MT4_TRADES SET VOLUME = 0, CLOSE_TIME = %s, CLOSE_PRICE = OPEN_PRICE, CONV_RATE2 = %s, "
            "COMMISSION = 0, COMMISSION_AGENT = 0, SWAPS = 0, PROFIT = 0, COMMENT = %s "
            "WHERE SERVER = 'trade/mt4' AND TICKET = %s",
            (done, conv2, f"close by hedge: {main['TICKET']}", other["TICKET"]))
        log.append(f"ticket {main['TICKET']} closed by {other['TICKET']} at {close_price}: "
                   f"{main['VOLUME'] / 100:g} lots, P/L {pl}")
    return log


GIVEUP_SYMBOL_SQL = ("SELECT r.MT4_SYMBOL, s.DIGITS, s.CURRENCY AS BASE, u.CURRENCY AS DEPOSIT, gs.COMM_BASE, "
                     "s.CONTRACT_SIZE, r.CONTRACTS_PER_LOT, r.SCALING_MULTIPLIER "
                     "FROM mt4.MT4_USERS u "
                     "JOIN reference.mt4_symbol_reference r ON r.XCORE_SYMBOL = %s "
                     "JOIN mt4.MT4_SYMBOLS s ON s.SERVER = u.SERVER AND s.SYMBOL = r.MT4_SYMBOL "
                     "JOIN mt4.MT4_GROUP_SECURITIES gs ON gs.SERVER = u.SERVER AND gs.`GROUP` = u.`GROUP` "
                     "AND gs.SEC_INDEX = s.TYPE "
                     "WHERE u.SERVER = 'trade/mt4' AND u.LOGIN = %s")


def book_leg(cur, g: dict, when: datetime, rng: random.Random) -> list[str]:
    """Put one giveup row on the giveup login's MT4 tickets: close opposite
    tickets FIFO (partially closing the last one if needed), then open a ticket
    for anything left. Comments chain XCore order IDs (domain notes, "MT4
    trade behaviour: API logins")."""
    login, order_id, side = g["GIVEUP_LOGIN"], g["ORDER_ID"], g["GIVEUP_SIDE"]
    cur.execute(GIVEUP_SYMBOL_SQL, (g["SYMBOL"], login))
    cols = [c[0] for c in cur.description]
    sym = dict(zip(cols, cur.fetchall()[0]))
    deposit = sym["DEPOSIT"]
    quote = g["SYMBOL"].split("/")[1] if "/" in g["SYMBOL"] else "USD"
    price = dec(g["GIVEUP_PRICE"])
    volume = int(dec(g["LegFillSize"]) / lot_contracts(sym, "0.01"))
    done = when.strftime("%Y-%m-%d %H:%M:%S")
    comm_rate = -Decimal(sym["COMM_BASE"]) * dec(sym["CONTRACT_SIZE"]) / 100 / 100_000   # per volume unit, per side

    cur.execute("SELECT TICKET FROM mt4.MT4_TRADES WHERE SERVER = 'trade/mt4' AND LOGIN = %s AND SYMBOL = %s "
                "AND CMD = %s AND CLOSE_TIME = %s ORDER BY OPEN_TIME, TICKET",
                (login, sym["MT4_SYMBOL"], 1 if side == "buy" else 0, OPEN_DATE))
    opposite = [load_ticket(cur, n) for (n,) in cur.fetchall()]
    log, remaining = [], volume
    conv2 = rate(sym["BASE"], deposit, quote, price)
    for t in opposite:
        if not remaining:
            break
        if t["VOLUME"] > remaining:
            child = partial_close(cur, t, remaining, f"f{t['TICKET']}")
            log.append(f"  ticket {t['TICKET']} partially closed: {child['VOLUME'] / 100:g} lots to child "
                       f"{child['TICKET']}")
        t_side = "buy" if t["CMD"] == 0 else "sell"
        pl = profit(t_side, contracts(t, t["VOLUME"]), t["OPEN_PRICE"], price, conv2, deposit)
        commission = t["COMMISSION"] + money(comm_rate * t["VOLUME"] * conv2, deposit)
        cur.execute(
            "UPDATE mt4.MT4_TRADES SET VOLUME = %s, CLOSE_TIME = %s, CLOSE_PRICE = %s, CONV_RATE2 = %s, "
            "COMMISSION = %s, PROFIT = %s, COMMENT = CONCAT(COMMENT, ':', %s) "
            "WHERE SERVER = 'trade/mt4' AND TICKET = %s",
            (t["VOLUME"], done, price, conv2, commission, pl, order_id, t["TICKET"]))
        log.append(f"  ticket {t['TICKET']} closed: {t['VOLUME'] / 100:g} lots at {price}, P/L {pl}")
        remaining -= t["VOLUME"]
    if remaining:
        ticket = next_ticket(cur)
        conv1 = rate(sym["BASE"], deposit, quote, price)
        mid = (Decimal(MIDS[g["SYMBOL"]]) * dec(1 + rng.gauss(0, 0.0005))).quantize(Decimal(1).scaleb(-sym["DIGITS"]))
        floating = close_quote(dict(DIGITS=sym["DIGITS"], XCORE_SYMBOL=g["SYMBOL"], SPREAD_DIFF=0,
                                    MARKUP_BID=0, MARKUP_ASK=0), side, mid)
        size = Decimal(remaining) / 100 * dec(sym["CONTRACT_SIZE"])
        pl = profit(side, size, price, floating, rate(sym["BASE"], deposit, quote, floating), deposit)
        cur.execute(
            "INSERT INTO mt4.MT4_TRADES (SERVER, TICKET, LOGIN, SYMBOL, DIGITS, CMD, VOLUME, OPEN_TIME, OPEN_PRICE, "
            "CLOSE_TIME, CLOSE_PRICE, CONV_RATE1, CONV_RATE2, COMMISSION, COMMISSION_AGENT, SWAPS, PROFIT, COMMENT) "
            "VALUES ('trade/mt4', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, 0, 0, %s, %s)",
            (ticket, login, sym["MT4_SYMBOL"], sym["DIGITS"], 0 if side == "buy" else 1, remaining, done, price,
             OPEN_DATE, floating, conv1, money(comm_rate * remaining * conv1, deposit), pl, str(order_id)))
        log.append(f"  ticket {ticket} opened: {side} {remaining / 100:g} lots at {price}")
    return log


def book_order(cur, order_id: int, rng: random.Random) -> list[str]:
    """XCore originates API login tickets: run the giveups and book this
    order's API giveup rows, one per filled leg, in leg order."""
    cur.callproc("reporting.giveup")
    cur.execute("SELECT g.*, o.CLOSE_MILLI FROM reporting.giveup_trades g "
                "JOIN xcore.XCORE_ORDER o ON o.ORDER_ID = g.ORDER_ID "
                "WHERE g.ORDER_ID = %s AND g.CONNECTOR <> 'trade/mt4' ORDER BY g.LEG_ID, g.GIVEUP_ID", (order_id,))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    log = [f"order {order_id}: no API giveup rows"] if not rows else []
    for g in rows:
        when = datetime.fromtimestamp(g["CLOSE_MILLI"] // 1000, tz=timezone.utc)
        log.append(f"order {order_id} leg {g['LEG_ID']} -> login {g['GIVEUP_LOGIN']}: {g['GIVEUP_SIDE']} "
                   f"{g['LegFillSize']:f} {g['SYMBOL']} at {g['GIVEUP_PRICE']}")
        log += book_leg(cur, g, when, rng)
    return log


def api_order(cur, account: str, symbol: str, side: str, lots: str, when: datetime, rng: random.Random) -> list[str]:
    """An API client's order through the bridge simulation, then its giveup tickets."""
    cur.execute(API_SQL + " AND acct.name = %s AND pool.xcore_symbol = %s", (account, symbol))
    cols = [c[0] for c in cur.description]
    row = dict(zip(cols, cur.fetchall()[0]))
    point = Decimal(1).scaleb(-int(row["DIGITS"]))
    mid = (Decimal(MIDS[symbol]) * dec(1 + rng.gauss(0, 0.0005))).quantize(point)
    ms = int(when.replace(tzinfo=timezone.utc).timestamp() * 1000)
    ex = execute(row, side, lot_contracts(row, lots), False, ms, mid, rng, None)
    order_id = save_api(cur, row, ex)
    return [f"{account} {side} {lots} {symbol}: order {order_id} filled {ex.fillsize:f}"] + book_order(cur, order_id, rng)


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
    h = sub.add_parser("hedge", help="close open tickets against each other (close by hedge)")
    h.add_argument("--tickets", type=int, nargs="+", required=True)
    h.add_argument("--time", type=datetime.fromisoformat, required=True, help="GMT time the process completes")
    h.add_argument("--seed", type=int)
    a = sub.add_parser("api", help="an API client's order, booked onto its giveup login's tickets")
    a.add_argument("--account", required=True, help="XCore connector account, e.g. uk_cov_100")
    a.add_argument("--symbol", required=True, help="XCore symbol, e.g. EUR/USD")
    a.add_argument("--side", choices=("buy", "sell"), required=True)
    a.add_argument("--lots", required=True)
    a.add_argument("--time", type=datetime.fromisoformat, required=True, help="GMT request time")
    a.add_argument("--seed", type=int)
    b = sub.add_parser("book", help="book existing XCore orders onto their API giveup logins' tickets")
    b.add_argument("--orders", type=int, nargs="+", required=True)
    b.add_argument("--seed", type=int)
    args = parser.parse_args()

    conn = connect()
    cur = conn.cursor()
    rng = random.Random(args.seed)
    if args.action == "open":
        print(open_trade(cur, args.login, args.symbol, args.side, args.lots, args.time, rng))
    elif args.action == "hedge":
        print("\n".join(close_by_hedge(cur, args.tickets, args.time, rng)))
    elif args.action == "api":
        print("\n".join(api_order(cur, args.account, args.symbol, args.side, args.lots, args.time, rng)))
    else:
        print("\n".join(line for o in args.orders for line in book_order(cur, o, rng)))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
