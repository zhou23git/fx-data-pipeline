"""Create retail MT4 accounts (logins 1000-8999) in mt4.MT4_USERS.

First batch:  python -m fxgen.accounts --date 2026-10-22 --count 500
Daily run:    python -m fxgen.accounts --date 2026-10-23

Without --count, a daily run makes 2-8 accounts. Retail groups and rebate
logins are read from MySQL. Connection: MYSQL_HOST, MYSQL_PORT, MYSQL_USER,
MYSQL_PASSWORD.
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from datetime import date, datetime, timedelta

from fxgen.db import connect
from fxgen.reference import FIRST_NAMES, LAST_NAMES

SERVER = "trade/mt4"
RETAIL_FIRST, RETAIL_LAST = 1000, 8999
CURRENCY_WEIGHTS = {"USD": 50, "EUR": 20, "GBP": 18, "JPY": 12}
REBATE_SHARE = 0.025
# Invented numbers: UK uses Ofcom's 07700 900xxx drama range.
PHONE_FORMATS = [("+64 21 555 ", 4), ("+44 7700 900", 3)]


def retail_groups(cur) -> dict[str, str]:
    cur.execute(
        "SELECT CURRENCY, `GROUP` FROM mt4.MT4_GROUPS WHERE SERVER = %s AND `GROUP` LIKE 'Retail%%'",
        (SERVER,),
    )
    groups = dict(cur.fetchall())
    missing = set(CURRENCY_WEIGHTS) - set(groups)
    if missing:
        sys.exit(f"No retail group in MT4_GROUPS for: {', '.join(sorted(missing))}")
    return groups


def rebate_logins(cur) -> list[int]:
    cur.execute(
        "SELECT LOGIN FROM mt4.MT4_USERS WHERE SERVER = %s AND `GROUP` = 'Rebate' ORDER BY LOGIN",
        (SERVER,),
    )
    return [row[0] for row in cur.fetchall()]


def next_login(cur) -> int:
    cur.execute(
        "SELECT MAX(LOGIN) FROM mt4.MT4_USERS WHERE SERVER = %s AND LOGIN BETWEEN %s AND %s",
        (SERVER, RETAIL_FIRST, RETAIL_LAST),
    )
    last = cur.fetchone()[0]
    return RETAIL_FIRST if last is None else last + 1


def make_accounts(rng: random.Random, day: date, count: int, first_login: int,
                  groups: dict[str, str], rebates: list[int]) -> list[tuple]:
    currencies = rng.choices(list(CURRENCY_WEIGHTS), weights=list(CURRENCY_WEIGHTS.values()), k=count)
    # Sorted so later logins register later in the day, as on a real server.
    seconds = sorted(rng.randrange(86_400) for _ in range(count))
    rows = []
    for i, (ccy, sec) in enumerate(zip(currencies, seconds)):
        prefix, digits = rng.choice(PHONE_FORMATS)
        agent = rng.choice(rebates) if rebates and rng.random() < REBATE_SHARE else 0
        rows.append((
            SERVER,
            first_login + i,
            groups[ccy],
            f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            "NZ_TRD",
            prefix + str(rng.randrange(10 ** digits)).zfill(digits),
            "Retail Clients",
            agent,
            ccy,
            datetime.combine(day, datetime.min.time()) + timedelta(seconds=sec),
        ))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="registration date, GMT (default: today)")
    parser.add_argument("--count", type=int, help="accounts to create (default: 2-8)")
    args = parser.parse_args()

    conn = connect()
    cur = conn.cursor()
    groups = retail_groups(cur)
    rebates = rebate_logins(cur)
    first = next_login(cur)

    # Seeded by date and first login, so a rerun against the same state repeats itself.
    rng = random.Random(f"{args.date}:{first}")
    count = args.count if args.count is not None else rng.randint(2, 8)
    if first + count - 1 > RETAIL_LAST:
        sys.exit(f"Retail range full: {RETAIL_LAST - first + 1} logins left, {count} requested.")

    rows = make_accounts(rng, args.date, count, first, groups, rebates)
    cur.executemany(
        "INSERT INTO mt4.MT4_USERS (SERVER, LOGIN, `GROUP`, NAME, LEAD_SOURCE, PHONE, COMMENT, "
        "AGENT_ACCOUNT, CURRENCY, REGDATE) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    conn.commit()
    conn.close()

    by_ccy = Counter(r[8] for r in rows)
    flagged = sum(1 for r in rows if r[7])
    print(f"Created {count} retail accounts, logins {first}-{first + count - 1}, on {args.date}.")
    print("By currency: " + ", ".join(f"{c} {n}" for c, n in sorted(by_ccy.items())))
    print(f"Paying rebate: {flagged}")


if __name__ == "__main__":
    main()
