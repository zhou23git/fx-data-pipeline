"""Daily client statements as CSV, one file per login per trading day, and
their summary rows in mt4.MT4_DAILY.

  python -m fxgen.statements --date 2026-10-30 --login 1227

A trading day D runs from 17:00 New York on D-1 to 17:00 New York on D.
Josh's layout, in order:
  1. header: login, statement date (yyyy-mm-dd), name, currency;
  2. closed tickets: buys and sells closed during the day, with commission,
     swaps and profit as stored in MT4_TRADES;
  3. open tickets at the close;
  4. summary:
     - previous balance: the new balance of the login's last statement;
     - deposits: the day's deposits and withdrawals (CMD 6), net;
     - profit_closed: commission + swaps + profit of the closed tickets;
     - new balance: previous balance + deposits + profit_closed;
     - profit_open: commission + swaps + profit of the open tickets;
     - P/L: new balance + profit_open.
The summary is also written to MT4_DAILY, one row per login per statement.
A login's first statement takes its previous balance from its transactions
before the day, since it has no earlier statement.

Open tickets show their stored CLOSE_PRICE and PROFIT, which end of day
marks to the price snapshot just before writing statements, so a statement
is only right for the day it is generated at end of day. Files go to
out/statements/<date>/<login>.csv. Josh uses them as the source of truth
for open positions at end of day and to work out end-of-day conversion
rates.
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
TYPES = {0: "buy", 1: "sell"}
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
                "CMD IN (0, 1) AND " + where + f" ORDER BY {order}, TICKET", params)
    return [[ticket, f"{opened:%Y-%m-%d %H:%M:%S}", TYPES[cmd], f"{volume / 100:.2f}", symbol, open_price,
             f"{closed:%Y-%m-%d %H:%M:%S}" if closed != datetime(1970, 1, 1) else "", close_price, comm, swaps,
             profit, comment]
            for ticket, opened, cmd, volume, symbol, open_price, closed, close_price, comm, swaps, profit, comment
            in cur.fetchall()]


def costs(rows: list[list]) -> Decimal:
    """Commission + swaps + profit of a ticket list."""
    return sum((Decimal(str(r[8])) + Decimal(str(r[9])) + Decimal(str(r[10])) for r in rows), Decimal(0))


def previous_balance(cur, login: int, day: date, start: datetime) -> Decimal:
    """The new balance of the login's last statement; for a first statement,
    its balance from transactions before the day."""
    cur.execute("SELECT NEW_BALANCE FROM mt4.MT4_DAILY WHERE SERVER = 'trade/mt4' AND LOGIN = %s "
                "AND STATEMENT_DATE < %s ORDER BY STATEMENT_DATE DESC LIMIT 1", (login, day))
    row = cur.fetchone()
    return Decimal(str(row[0])) if row else balance_at(cur, login, start)


def write_statement(cur, login: int, day: date, out: Path = OUT) -> Path:
    start, end = day_bounds(day)
    cur.execute("SELECT NAME, CURRENCY FROM mt4.MT4_USERS WHERE SERVER = 'trade/mt4' AND LOGIN = %s", (login,))
    name, currency = cur.fetchone()
    previous = previous_balance(cur, login, day, start)
    closed = tickets(cur, "CLOSE_TIME >= %s AND CLOSE_TIME < %s", (login, start, end), "CLOSE_TIME")
    open_ = tickets(cur, "OPEN_TIME < %s AND (CLOSE_TIME = %s OR CLOSE_TIME >= %s)", (login, end, OPEN_DATE, end),
                    "OPEN_TIME")
    cur.execute("SELECT COALESCE(SUM(PROFIT), 0) FROM mt4.MT4_TRADES WHERE SERVER = 'trade/mt4' AND LOGIN = %s "
                "AND CMD = 6 AND OPEN_TIME >= %s AND OPEN_TIME < %s", (login, start, end))
    deposits = Decimal(str(cur.fetchone()[0]))
    profit_closed, profit_open = costs(closed), costs(open_)
    new = previous + deposits + profit_closed
    summary = [("PREVIOUS_BALANCE", previous), ("DEPOSITS", deposits), ("PROFIT_CLOSED", profit_closed),
               ("NEW_BALANCE", new), ("PROFIT_OPEN", profit_open), ("PL", new + profit_open)]

    path = out / f"{day:%Y-%m-%d}" / f"{login}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["LOGIN", "STATEMENT_DATE", "NAME", "CURRENCY"])
        w.writerow([login, f"{day:%Y-%m-%d}", name, currency])
        w.writerow([])
        w.writerow(["CLOSED_TICKETS"])
        w.writerow(TICKET_COLS)
        w.writerows(closed)
        w.writerow([])
        w.writerow(["OPEN_TICKETS"])
        w.writerow(TICKET_COLS)
        w.writerows(open_)
        w.writerow([])
        w.writerow(["SUMMARY"])
        w.writerows([label, f"{value:.2f}"] for label, value in summary)
    cur.execute("REPLACE INTO mt4.MT4_DAILY (SERVER, LOGIN, STATEMENT_DATE, PREVIOUS_BALANCE, DEPOSITS, PROFIT_CLOSED, "
                "NEW_BALANCE, PROFIT_OPEN, PL) VALUES ('trade/mt4', %s, %s, %s, %s, %s, %s, %s, %s)",
                (login, day, *(round(value, 2) for _, value in summary)))
    return path


def write_statements(cur, day: date, out: Path = OUT) -> list[str]:
    """End of day: a statement and MT4_DAILY row for every login with an open
    ticket at the close or any transaction during the day."""
    start, end = day_bounds(day)
    cur.execute("SELECT DISTINCT LOGIN FROM mt4.MT4_TRADES WHERE SERVER = 'trade/mt4' AND ("
                "(CMD IN (0, 1) AND OPEN_TIME < %s AND (CLOSE_TIME = %s OR CLOSE_TIME >= %s)) "
                "OR (CMD IN (0, 1) AND CLOSE_TIME >= %s AND CLOSE_TIME < %s) "
                "OR (CMD = 6 AND OPEN_TIME >= %s AND OPEN_TIME < %s)) ORDER BY LOGIN",
                (end, OPEN_DATE, end, start, end, start, end))
    logins = [login for (login,) in cur.fetchall()]
    for login in logins:
        write_statement(cur, login, day, out)
    return [f"{len(logins)} statements for {day:%Y-%m-%d} in {out / f'{day:%Y-%m-%d}'}"]


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
