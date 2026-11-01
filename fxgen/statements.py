"""Daily client statements as CSV, one file per login per trading day.

  python -m fxgen.statements --date 2026-10-30 --login 1227

A trading day D runs from 17:00 New York on D-1 to 17:00 New York on D. Each
statement has, in order:
  1. the header: login, name, currency, trading day and its GMT bounds;
  2. the previous balance (at the start of the day);
  3. closed transactions: tickets closed during the day, plus deposits and
     withdrawals (CMD 6), which MT4 treats as closed tickets;
  4. open tickets at the end of the day;
  5. the new balance: previous balance + closed transactions' profit,
     commission and swaps.

Open tickets show their stored CLOSE_PRICE and PROFIT, so a statement is
only right for the day it is generated at end of day. Files go to
out/statements/<date>/<login>.csv.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from fxgen.db import connect
from fxgen.mt4trades import OPEN_DATE

NEW_YORK, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")
OUT = Path("out/statements")
TYPES = {0: "buy", 1: "sell", 6: "balance", 7: "credit"}
TICKET_COLS = ("TICKET", "OPEN_TIME", "TYPE", "LOTS", "SYMBOL", "OPEN_PRICE", "CLOSE_TIME", "CLOSE_PRICE",
               "COMMISSION", "SWAPS", "PROFIT", "COMMENT")


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """GMT start and end of trading day `day` (17:00 New York to 17:00 New York)."""
    end = datetime.combine(day, time(17), NEW_YORK).astimezone(UTC).replace(tzinfo=None)
    start = datetime.combine(day - timedelta(days=1), time(17), NEW_YORK).astimezone(UTC).replace(tzinfo=None)
    return start, end


def balance_at(cur, login: int, when: datetime) -> Decimal:
    """Cash balance at `when`: balance rows plus closed tickets' profit, commission and swaps."""
    cur.execute("SELECT COALESCE(SUM(PROFIT + COMMISSION + SWAPS), 0) FROM mt4.MT4_TRADES "
                "WHERE SERVER = 'trade/mt4' AND LOGIN = %s AND ((CMD = 6 AND OPEN_TIME < %s) "
                "OR (CMD IN (0, 1) AND CLOSE_TIME <> %s AND CLOSE_TIME < %s))", (login, when, OPEN_DATE, when))
    return Decimal(str(cur.fetchone()[0]))


def tickets(cur, where: str, params: tuple, order: str) -> list[list]:
    cur.execute("SELECT TICKET, OPEN_TIME, CMD, VOLUME, SYMBOL, OPEN_PRICE, CLOSE_TIME, CLOSE_PRICE, COMMISSION, "
                "SWAPS, PROFIT, COMMENT FROM mt4.MT4_TRADES WHERE SERVER = 'trade/mt4' AND LOGIN = %s AND "
                + where + f" ORDER BY {order}, TICKET",
                params)
    rows = []
    for ticket, opened, cmd, volume, symbol, open_price, closed, close_price, comm, swaps, profit, comment in cur:
        trade = cmd in (0, 1)
        rows.append([ticket, f"{opened:%Y-%m-%d %H:%M:%S}", TYPES.get(cmd, cmd),
                     f"{volume / 100:.2f}" if trade else "", symbol, open_price if trade else "",
                     f"{closed:%Y-%m-%d %H:%M:%S}" if closed != datetime(1970, 1, 1) else "",
                     close_price if trade else "", comm, swaps, profit, comment])
    return rows


def write_statement(cur, login: int, day: date, out: Path = OUT) -> Path:
    start, end = day_bounds(day)
    cur.execute("SELECT NAME, CURRENCY, `GROUP` FROM mt4.MT4_USERS WHERE SERVER = 'trade/mt4' AND LOGIN = %s", (login,))
    name, currency, group = cur.fetchone()
    previous = balance_at(cur, login, start)
    closed = tickets(cur, "((CMD IN (0, 1) AND CLOSE_TIME >= %s AND CLOSE_TIME < %s) "
                          "OR (CMD = 6 AND OPEN_TIME >= %s AND OPEN_TIME < %s))", (login, start, end, start, end),
                     "CLOSE_TIME")
    open_ = tickets(cur, "CMD IN (0, 1) AND OPEN_TIME < %s AND (CLOSE_TIME = %s OR CLOSE_TIME >= %s)",
                    (login, end, OPEN_DATE, end), "OPEN_TIME")
    new = previous + sum((Decimal(str(r[8])) + Decimal(str(r[9])) + Decimal(str(r[10])) for r in closed), Decimal(0))

    path = out / f"{day:%Y-%m-%d}" / f"{login}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["STATEMENT", "LOGIN", "NAME", "GROUP", "CURRENCY", "TRADING_DAY", "FROM_GMT", "TO_GMT"])
        w.writerow(["", login, name, group, currency, f"{day:%Y-%m-%d}", f"{start:%Y-%m-%d %H:%M:%S}",
                    f"{end:%Y-%m-%d %H:%M:%S}"])
        w.writerow([])
        w.writerow(["PREVIOUS_BALANCE", f"{previous:.2f}"])
        w.writerow([])
        w.writerow(["CLOSED_TRANSACTIONS"])
        w.writerow(TICKET_COLS)
        w.writerows(closed)
        w.writerow([])
        w.writerow(["OPEN_TICKETS"])
        w.writerow(TICKET_COLS)
        w.writerows(open_)
        w.writerow([])
        w.writerow(["NEW_BALANCE", f"{new:.2f}"])
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", type=date.fromisoformat, required=True, help="trading day (ends 17:00 New York)")
    parser.add_argument("--login", type=int, required=True)
    args = parser.parse_args()
    conn = connect()
    print(write_statement(conn.cursor(), args.login, args.date))
    conn.close()


if __name__ == "__main__":
    main()
