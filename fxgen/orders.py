"""Simulate MT4 -> XCore executions into XCORE_ORDER_MT4, XCORE_ORDER and XCORE_LEG.

  python -m fxgen.orders sample --date 2026-10-26 [--replace]

sample writes one showcase set per scenario in SAMPLE (open and, if filled,
close), so every behaviour can be checked by eye. Rules are in
docs/domain-notes.md, "Execution tables". Tradeable logins, symbols, pools,
providers, markups and B-book come from Josh's query over the bridge output
(reference.connector_account_logins); run the bridge first.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from fxgen.db import connect

TRADABLE_SQL = """
SELECT mt4.*,
       sym.XCORE_SYMBOL, sym.DIGITS, sym.POINT, sym.CONTRACTS_PER_LOT, sym.SCALING_MULTIPLIER,
       prof.MARKUP_BID, prof.MARKUP_ASK, prof.B_BOOK,
       pool.PROVIDER_ID
FROM reference.connector_account_logins mt4
left join reference.symbol_reference sym
on mt4.symbol = sym.mt4_symbol
left join xcore.xcore_liquidity_pool_providers pool
on mt4.pool_id = pool.pool_id
and sym.XCORE_SYMBOL = pool.XCORE_SYMBOL
left join xcore.xcore_profile_symbols prof
on mt4.profile_id = prof.profile_id
and sym.XCORE_SYMBOL = prof.XCORE_SYMBOL
"""

# Fake mids per XCore symbol, and half the raw spread in points.
MIDS = {
    "EUR/USD": "1.08512", "GBP/USD": "1.27034", "AUD/USD": "0.65871", "NZD/USD": "0.59342",
    "USD/JPY": "151.234", "USD/CHF": "0.86421", "USD/CAD": "1.38215", "EUR/GBP": "0.85418",
    "EUR/JPY": "164.112", "GBP/JPY": "192.115", "AUD/JPY": "99.618", "CAD/JPY": "109.418",
    "EUR/CHF": "0.93774", "XAU/USD": "2734.15", "XAG/USD": "33.71", "WTI": "71.42",
    "Brent": "75.63", "Nasdaq": "20412.35", "SP500": "5806.18",
}
HALF_SPREAD_POINTS = {"XAU/USD": 12, "Nasdaq": 40, "SP500": 25}  # default 3
PROVIDER_EDGE_POINTS = {1: 0, 3: 0, 2: 2, 4: 2}   # how far each provider quotes off the best
BOOK_LEVELS, LEVEL_LOTS = 4, 10                     # depth per provider; each level 1 point worse
MAX_LEGS = 6
SLIP_CHANCE, ADVERSE_SHARE = 0.4, 0.95
FIRST_TICKET = 1_000_001

# One showcase set per row: who trades what, and which behaviour to force.
SAMPLE = [
    dict(name="normal",         account="Retail", symbol="EURUSD.retail", side="buy",  lots="0.5"),
    dict(name="sweep",          account="B2B",    symbol="EURUSD.b2b",    side="sell", lots="25"),
    dict(name="reject_retry",   account="B2B",    symbol="GBPUSD.b2b",    side="buy",  lots="3"),
    dict(name="reject_all",     account="B2B",    symbol="USDJPY.b2b",    side="buy",  lots="2"),
    dict(name="partial",        account="B2B",    symbol="AUDUSD.b2b",    side="sell", lots="4"),
    dict(name="hidden",         account="House",  symbol="EURUSD",        side="buy",  lots="1", login=20),
    dict(name="good_slip",      account="House",  symbol="USDCAD",        side="sell", lots="2", login=50),
    dict(name="metal_bbook",    account="WL",     symbol="XAUUSD",        side="buy",  lots="1"),
    dict(name="mini_cfd",       account="Retail", symbol="NAS100",        side="buy",  lots="2"),
    dict(name="close_rejected", account="B2B",    symbol="EURJPY.b2b",    side="buy",  lots="5"),
]


@dataclass
class Leg:
    leg_id: int
    b_book: int
    amount: Decimal
    price: Decimal
    fillsize: Decimal
    fillprice1: Decimal
    fillprice2: Decimal
    lp: int
    markup_bid: Decimal
    markup_ask: Decimal
    open_ms: int
    close_ms: int


@dataclass
class Execution:
    side: str
    amount: Decimal
    price: Decimal
    mt4_price: Decimal
    open_ms: int
    mt4_open_ms: int
    legs: list[Leg] = field(default_factory=list)

    @property
    def fillsize(self) -> Decimal:
        return sum((leg.fillsize for leg in self.legs), Decimal(0))

    @property
    def fillprice(self) -> Decimal:
        if not self.fillsize:
            return Decimal(0)
        vwap = sum(leg.fillsize * leg.fillprice2 for leg in self.legs) / self.fillsize
        return vwap.quantize(Decimal("1e-12"))

    @property
    def close_ms(self) -> int:
        return max(leg.close_ms for leg in self.legs)


def dec(x) -> Decimal:
    return Decimal(str(x))


def lot_contracts(row: dict, lots) -> Decimal:
    return (dec(lots) * dec(row["CONTRACTS_PER_LOT"]) * dec(row["SCALING_MULTIPLIER"])).quantize(Decimal("1e-6"))


def book(row: dict, side: str, mid: Decimal, point: Decimal, rng: random.Random) -> list[tuple]:
    """Every (price, provider, size) level the pool offers, best first for this side."""
    half = HALF_SPREAD_POINTS.get(row["XCORE_SYMBOL"], 3)
    size = lot_contracts(row, LEVEL_LOTS)
    sign = 1 if side == "buy" else -1
    levels = []
    for pid in (int(p) for p in row["PROVIDER_ID"].split(",")):
        top = half + PROVIDER_EDGE_POINTS.get(pid, 2) + rng.choice((0, 0, 1))
        for k in range(BOOK_LEVELS):
            levels.append((mid + sign * (top + k) * point, pid, size))
    return sorted(levels, key=lambda lv: (sign * lv[0], lv[1]))


def execute(row: dict, side: str, amount: Decimal, is_close: bool, mt4_open_ms: int, mid: Decimal,
            rng: random.Random, force: str | None) -> Execution:
    point = Decimal(1).scaleb(-int(row["DIGITS"]))
    sign = 1 if side == "buy" else -1
    markup = row["MARKUP_ASK"] if side == "buy" else row["MARKUP_BID"]
    gm_points = (row["SPREAD_DIFF"] // 2) if is_close else math.ceil(row["SPREAD_DIFF"] / 2)
    levels = book(row, side, mid, point, rng)
    top = levels[0][0]
    ex = Execution(side, amount, top + markup, top + markup + sign * gm_points * point,
                   mt4_open_ms + rng.randint(2, 8), mt4_open_ms)
    lot_step = lot_contracts(row, row["LOT_STEP"])

    remaining, t_next = amount, ex.open_ms + rng.randint(1, 4)
    for leg_id, (price, pid, size) in enumerate(levels[:MAX_LEGS]):
        if remaining <= 0:
            break
        leg_amount = min(remaining, size)
        open_ms = t_next
        close_ms = open_ms + rng.randint(15, 120)
        fill, slip, stop = leg_amount, 0, False
        if not row["B_BOOK"]:
            if force == "reject_all" or (force == "reject_retry" and leg_id == 0):
                fill = Decimal(0)
            elif force == "partial":
                fill, stop = leg_amount - lot_step * rng.randint(1, int(leg_amount / lot_step) - 1), True
            elif force == "hidden":
                fill, stop = (leg_amount * Decimal("0.735")).quantize(Decimal("1e-6")), True
            if fill:
                if force == "good_slip":
                    slip = -1
                elif rng.random() < SLIP_CHANCE:
                    slip = rng.randint(1, 2) if rng.random() < ADVERSE_SHARE else -1
        fp1 = price + sign * slip * point if fill else Decimal(0)
        ex.legs.append(Leg(leg_id, int(row["B_BOOK"]), leg_amount, price, fill, fp1,
                           fp1 + markup if fill else Decimal(0), pid,
                           row["MARKUP_BID"], row["MARKUP_ASK"], open_ms, close_ms))
        remaining -= fill
        # A rejection is retried after it comes back; sweep legs go out a few ms apart.
        t_next = (close_ms if not fill else open_ms) + rng.randint(1, 3)
        if stop:
            break
        if force == "reject_all" and leg_id == 2:
            break
    return ex


def mt4_fill(row: dict, ex: Execution, is_close: bool) -> tuple[Decimal, Decimal]:
    """MT4 floors the size to its lot step and rounds the price to DIGITS in the broker's favour."""
    if not ex.fillsize:
        return Decimal(0), Decimal(0)
    step = lot_contracts(row, row["LOT_STEP"])
    size = (ex.fillsize / step).to_integral_value(ROUND_FLOOR) * step
    point = Decimal(1).scaleb(-int(row["DIGITS"]))
    sign = 1 if ex.side == "buy" else -1
    gm_points = (row["SPREAD_DIFF"] // 2) if is_close else math.ceil(row["SPREAD_DIFF"] / 2)
    raw = ex.fillprice + sign * gm_points * point
    price = raw.quantize(point, rounding=ROUND_CEILING if ex.side == "buy" else ROUND_FLOOR)
    return size, price


def save(cur, row: dict, ex: Execution, ticket: int, is_close: bool) -> tuple[int, Decimal, int]:
    size, price = mt4_fill(row, ex, is_close)
    order_close = ex.close_ms + 2
    mt4_close = order_close + 3
    t = ticket if (size or is_close) else 0
    # MT4's request row comes first and gets the CLORDID; XCore receives it as
    # SUBID2, and the request row is then linked to the new order.
    cur.execute(
        "INSERT INTO xcore.XCORE_ORDER_MT4 (LOGIN, TICKET, `CLOSE`, SYMBOL, SIDE, AMOUNT, PRICE, FILLSIZE, FILLPRICE, "
        "OPEN_MILLI, CLOSE_MILLI) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (row["LOGIN"], t, int(is_close), row["SYMBOL"], ex.side, ex.amount, ex.mt4_price, size, price,
         ex.mt4_open_ms, mt4_close))
    clordid = cur.lastrowid
    cur.execute(
        "INSERT INTO xcore.XCORE_ORDER (SYMBOL, SIDE, CONNECTOR, ACCOUNT, SUBID1, SUBID2, SUBID3, SUBID4, AMOUNT, PRICE, "
        "FILLSIZE, FILLPRICE, OPEN_MILLI, CLOSE_MILLI) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (row["XCORE_SYMBOL"], ex.side, row["CONNECTOR"], row["CONNECTOR_ACCOUNT"], row["LOGIN"], clordid,
         row["GROUP"], row["LEAD_SOURCE"], ex.amount, ex.price, ex.fillsize, ex.fillprice, ex.open_ms, order_close))
    order_id = cur.lastrowid
    cur.execute("UPDATE xcore.XCORE_ORDER_MT4 SET ORDER_ID = %s WHERE CLORDID = %s", (order_id, clordid))
    for leg in ex.legs:
        cur.execute(
            "INSERT INTO xcore.XCORE_LEG (ORDER_ID, LEG_ID, B_BOOK, SYMBOL, SIDE, AMOUNT, PRICE, FILLSIZE, FILLPRICE1, "
            "FILLPRICE2, LP, MARKUP_BID, MARKUP_ASK, OPEN_MILLI, CLOSE_MILLI) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (order_id, leg.leg_id, leg.b_book, row["XCORE_SYMBOL"], ex.side, leg.amount, leg.price, leg.fillsize,
             leg.fillprice1, leg.fillprice2, leg.lp, leg.markup_bid, leg.markup_ask, leg.open_ms, leg.close_ms))
    return order_id, size, mt4_close


def run_sample(cur, day: date, rng: random.Random) -> list[str]:
    cur.execute(TRADABLE_SQL)
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=8)
    ticket, report = FIRST_TICKET, []
    for i, s in enumerate(SAMPLE):
        pick = [r for r in rows if r["CONNECTOR_ACCOUNT"] == s["account"] and r["SYMBOL"] == s["symbol"]
                and r["LOGIN"] == s.get("login", r["LOGIN"])]
        row = rng.choice(pick)
        mid = Decimal(MIDS[row["XCORE_SYMBOL"]])
        open_ms = int((start + timedelta(minutes=50 * i, seconds=rng.randint(0, 600))).timestamp() * 1000)
        amount = lot_contracts(row, s["lots"])
        ex = execute(row, s["side"], amount, False, open_ms, mid, rng, s["name"])
        oid, held, mt4_close = save(cur, row, ex, ticket, False)
        line = f"{s['name']:<15} login {row['LOGIN']:<6} {row['SYMBOL']:<14} {s['side']:<4} {s['lots']:>4} lots: order {oid} filled {ex.fillsize}/{amount}"
        if held:
            close_side = "sell" if s["side"] == "buy" else "buy"
            t = mt4_close + rng.randint(5, 240) * 60_000
            mid_close = (mid * dec(1 + rng.gauss(0, 0.0008))).quantize(Decimal(1).scaleb(-int(row["DIGITS"])))
            if s["name"] == "close_rejected":
                ex_c = execute(row, close_side, held, True, t, mid_close, rng, "reject_all")
                _, _, t = save(cur, row, ex_c, ticket, True)
                t += rng.randint(2_000, 8_000)
            ex_c = execute(row, close_side, held, True, t, mid_close, rng, "good_slip" if s["name"] == "good_slip" else None)
            save(cur, row, ex_c, ticket, True)
            line += f", MT4 ticket {ticket} holds {held}, closed"
            ticket += 1
        report.append(line)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("sample", help="write one showcase set per scenario")
    p.add_argument("--date", type=date.fromisoformat, default=date.today(), help="GMT trading day")
    p.add_argument("--replace", action="store_true", help="empty the three trade tables first")
    p.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM xcore.XCORE_ORDER")
    if cur.fetchone()[0] and not args.replace:
        sys.exit("Trade tables already have rows; use --replace to empty them first.")
    if args.replace:
        for table in ("XCORE_LEG", "XCORE_ORDER_MT4", "XCORE_ORDER"):
            cur.execute(f"DELETE FROM xcore.{table}")
        cur.execute("ALTER TABLE xcore.XCORE_ORDER AUTO_INCREMENT = 1")
        cur.execute("ALTER TABLE xcore.XCORE_ORDER_MT4 AUTO_INCREMENT = 1")
    for line in run_sample(cur, args.date, random.Random(args.seed)):
        print(line)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
