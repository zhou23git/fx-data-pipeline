"""The hourly process: one simulated hour of direct-client and API trading.

  python -m fxgen.hourly --start "2026-10-28 00:00" --hours 24 --seed 1

Each hour, as Josh runs it at about :55 (domain notes, "Hourly process"):

  Direct clients
  1. Run the bridge reference (reference.connector_account_login) for current
     trading conditions.
  2. Fetch open tickets and fully close a random subset (order MT4, XCore
     order and legs, ticket closed).
  3. Deposits and withdrawals for a random few clients.
  4. Open trades for a random set of bridge logins. A client with no
     deposit yet makes a first deposit just before its first trade.
  5. Fetch open tickets again and close some by hedge, at :55.

  API clients
  6. Run the API account reference.
  7. Place API orders (order and legs from the reference's markup, book and
     provider) until they are 40-50% of the hour's volume.
  8. Run the giveup procedure for the hour's orders.
  9. Book every giveup row onto its login's tickets (FIFO, partial closes).

  End of day (the 16:55 New York run, after its trades)
  10. Load the day's swap rates (mt4.MT4_SYMBOLS).
  11. Write the price snapshot (mt4.MT4_PRICES).
  12. Add one day's swap to every remaining open ticket (MT4_TRADES.SWAPS).

Times are simulated: events fall at random seconds between :00 and :55.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fxgen.db import connect
from fxgen.mt4trades import (DIRECT_OPEN_SQL, OPEN_DATE, api_order_row, balance, book_window, close_by_hedge,
                             close_trade, open_trade, rate)
from fxgen.orders import API_SQL, MIDS, TRADABLE_SQL, lot_contracts
from fxgen.prices import is_snapshot_run, snapshot_prices
from fxgen.swaps import charge_swaps, set_swaps

TRADE_CHANCE = 1 - 0.5 ** (1 / 24)   # per login per hour: about half the direct clients trade in a day
TRADES_PER_LOGIN = (1, 3)
CLOSE_CHANCE = 0.25                  # per open ticket per hour: about 90% are gone within 8 hours
HEDGE_CHANCE = 0.3                   # per login and symbol holding both sides
API_SHARE = (0.40, 0.50)             # API share of the hour's volume (USD notional)
DIRECT_LOTS = ["0.01", "0.05", "0.1", "0.2", "0.5", "1", "2", "3", "5"]
DIRECT_WEIGHTS = [10, 10, 20, 15, 15, 15, 8, 4, 3]
API_LOTS = ["1", "2", "3", "5", "10", "15", "20", "30"]
DEPOSIT_CHANCE = 1 / (24 * 14)       # per client per hour: a top-up about every two weeks
WITHDRAW_CHANCE = 1 / (24 * 30)      # per client per hour: a withdrawal about once a month
WITHDRAW_SHARE = (0.1, 0.5)          # of the client's balance
DEPOSIT_USD = {"B2B": ["50000", "100000", "250000", "500000"]}   # by group; others use the default
DEPOSIT_USD_DEFAULT = ["100", "250", "500", "1000", "2000", "5000", "10000"]
DEPOSIT_WEIGHTS = {"B2B": [4, 3, 2, 1]}
DEPOSIT_WEIGHTS_DEFAULT = [15, 20, 25, 20, 10, 7, 3]


def usd_notional(xcore_symbol: str, contracts: Decimal) -> Decimal:
    if "/" not in xcore_symbol:
        return contracts * Decimal(MIDS[xcore_symbol])
    base = xcore_symbol.split("/")[0]
    if base == "USD":
        return contracts
    if f"{base}/USD" in MIDS:
        return contracts * Decimal(MIDS[f"{base}/USD"])
    return contracts / Decimal(MIDS[f"USD/{base}"])


def pick_lots(row: dict, choices: list[str], weights: list[int] | None, rng: random.Random) -> Decimal:
    lots = Decimal(rng.choices(choices, weights)[0])
    step = Decimal(row["LOT_STEP"])
    lots = max(Decimal(row["LOT_MIN"]), min(Decimal(row["LOT_MAX"]), (lots / step).to_integral_value() * step))
    return lots


def at(hour: datetime, rng: random.Random) -> datetime:
    return hour + timedelta(seconds=rng.randint(0, 55 * 60 - 1))


def deposit_amount(group: str, currency: str, rng: random.Random) -> Decimal:
    """A round deposit in the client's currency, drawn in USD by group."""
    usd = Decimal(rng.choices(DEPOSIT_USD.get(group, DEPOSIT_USD_DEFAULT),
                              DEPOSIT_WEIGHTS.get(group, DEPOSIT_WEIGHTS_DEFAULT))[0])
    step = Decimal(1000 if currency == "JPY" else 10)
    return max(step, (usd * rate("USD", currency, "", Decimal(0)) / step).to_integral_value() * step)


def account_balance(cur, login: int, when: datetime) -> Decimal:
    """Balance at `when`: balance rows plus closed tickets' profit, commission and swaps."""
    done = when.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("SELECT COALESCE(SUM(PROFIT + COMMISSION + SWAPS), 0) FROM mt4.MT4_TRADES "
                "WHERE SERVER = 'trade/mt4' AND LOGIN = %s AND ((CMD = 6 AND OPEN_TIME <= %s) "
                "OR (CMD IN (0, 1) AND CLOSE_TIME <> %s AND CLOSE_TIME <= %s))", (login, done, OPEN_DATE, done))
    return Decimal(str(cur.fetchone()[0]))


def rows_of(cur) -> list[dict]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def run_hour(cur, hour: datetime, rng: random.Random) -> list[str]:
    log, direct_usd = [f"== {hour:%Y-%m-%d %H:00} GMT"], Decimal(0)

    # 1. bridge reference
    cur.callproc("reference.connector_account_login")
    cur.execute(TRADABLE_SQL)
    bridge = rows_of(cur)   # trading logins only; risk and coverage logins aren't in the bridge
    by_login = defaultdict(list)
    for r in bridge:
        by_login[r["LOGIN"]].append(r)
    xsym = {(r["LOGIN"], r["SYMBOL"]): r for r in bridge}

    # 2. close a random subset of open tickets
    cur.execute(DIRECT_OPEN_SQL)
    closes = [t for t in rows_of(cur) if (t["LOGIN"], t["SYMBOL"]) in xsym and rng.random() < CLOSE_CHANCE]
    for t in sorted(closes, key=lambda _: rng.random()):
        line, lots = close_trade(cur, t["TICKET"], at(hour, rng), rng)
        row = xsym[(t["LOGIN"], t["SYMBOL"])]
        direct_usd += usd_notional(row["XCORE_SYMBOL"], lot_contracts(row, lots))
        log.append("close  " + line)

    # 3. deposits and withdrawals by clients (House trading logins are funded internally)
    clients = {login: rows[0] for login, rows in by_login.items() if rows[0]["GROUP"] != "House"}
    cur.execute("SELECT DISTINCT LOGIN FROM mt4.MT4_TRADES WHERE SERVER = 'trade/mt4' AND CMD = 6")
    funded = {login for (login,) in cur.fetchall()}
    moves = []
    for login, row in clients.items():
        if login in funded and rng.random() < DEPOSIT_CHANCE:
            moves.append((at(hour, rng), login, deposit_amount(row["GROUP"], row["ACCOUNT_CURRENCY"], rng)))
        if login in funded and rng.random() < WITHDRAW_CHANCE:
            moves.append((at(hour, rng), login, None))
    for when, login, amount in sorted(moves, key=lambda m: m[0]):
        if amount is None:
            share = Decimal(str(rng.uniform(*WITHDRAW_SHARE)))
            amount = -(account_balance(cur, login, when) * share).quantize(Decimal(1))
            if amount >= 0:
                continue
        log.append("cash   " + balance(cur, login, str(amount), when, ""))

    # 4. new trades; a client's first trade comes after its first deposit
    events = []
    for login, rows in by_login.items():
        if rng.random() < TRADE_CHANCE:
            for _ in range(rng.randint(*TRADES_PER_LOGIN)):
                events.append((at(hour, rng), rng.choice(rows)))
    for when, row in sorted(events, key=lambda e: e[0]):
        if row["LOGIN"] in clients and row["LOGIN"] not in funded:
            first = hour + timedelta(seconds=rng.randint(0, int((when - hour).total_seconds())))
            amount = deposit_amount(row["GROUP"], row["ACCOUNT_CURRENCY"], rng)
            log.append("cash   " + balance(cur, row["LOGIN"], str(amount), first, ""))
            funded.add(row["LOGIN"])
        lots = pick_lots(row, DIRECT_LOTS, DIRECT_WEIGHTS, rng)
        log.append("open   " + open_trade(cur, row["LOGIN"], row["SYMBOL"], rng.choice(("buy", "sell")), str(lots),
                                         when, rng))
        direct_usd += usd_notional(row["XCORE_SYMBOL"], lot_contracts(row, lots))

    # 5. close by hedge at :55
    cur.execute(DIRECT_OPEN_SQL)
    positions = defaultdict(list)
    for t in rows_of(cur):
        positions[(t["LOGIN"], t["SYMBOL"])].append(t)
    for (login, symbol), ts in positions.items():
        if len({t["CMD"] for t in ts}) == 2 and rng.random() < HEDGE_CHANCE:
            log += ["hedge  " + line for line in
                    close_by_hedge(cur, [t["TICKET"] for t in ts], hour + timedelta(minutes=55), rng)]

    # 6-7. API orders up to their share of the hour's volume
    cur.execute(API_SQL)
    api_rows = [r for r in rows_of(cur) if r["PROVIDER_ID"] is not None]
    share = Decimal(str(rng.uniform(*API_SHARE)))
    target, api_usd, orders = direct_usd * share / (1 - share), Decimal(0), []
    while True:
        row = rng.choice(api_rows)
        lots = pick_lots(row, API_LOTS, None, rng)
        usd = usd_notional(row["XCORE_SYMBOL"], lot_contracts(row, lots))
        if api_usd + usd / 2 > target:   # stop at whichever side of the target is nearer
            break
        orders.append((at(hour, rng), row, lots))
        api_usd += usd
    for when, row, lots in sorted(orders, key=lambda o: o[0]):
        log.append("api    " + api_order_row(cur, row, rng.choice(("buy", "sell")), lots, when, rng)[0])

    # 8-9. giveups for the hour, booked in order-time order
    log += ["giveup " + line for line in book_window(cur, hour, hour + timedelta(hours=1), rng)
            if not line.startswith("order ")]
    # 10-12. end of day, on the 16:55 New York run after that hour's trades: the day's swap rates,
    # the price snapshot, then one day's swap on every open ticket
    eod = hour + timedelta(minutes=55)
    if is_snapshot_run(eod):
        log += ["swap   " + line for line in set_swaps(cur, rng)]
        log += ["price  " + line for line in snapshot_prices(cur, eod, rng)]
        log += ["swap   " + line for line in charge_swaps(cur, eod)]
    log.append(f"direct {direct_usd:,.0f} USD, API {api_usd:,.0f} USD "
               f"({api_usd / (direct_usd + api_usd) * 100 if direct_usd + api_usd else 0:.0f}%)")
    return log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True, help="first GMT hour")
    parser.add_argument("--hours", type=int, default=1)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--verbose", action="store_true", help="print every event, not just the summary")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    conn = connect()
    cur = conn.cursor()
    hour = args.start.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    for _ in range(args.hours):
        log = run_hour(cur, hour, rng)
        conn.commit()
        print("\n".join(log if args.verbose else [log[0], log[-1]]))
        hour += timedelta(hours=1)
    conn.close()


if __name__ == "__main__":
    main()
