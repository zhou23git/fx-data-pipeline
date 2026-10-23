"""Change XCore profile settings per symbol (markup, pool) and log each change.

  python -m fxgen.profiles set --profile Retail --symbol EUR/USD GBP/USD --markup 0.00003
  python -m fxgen.profiles set --profile Toxic --symbol XAU/USD --pool Bank_FX --time "2026-10-23 09:30:00"
  python -m fxgen.profiles random --date 2026-10-23

--markup is the size of the markup: the bid gets -markup, the ask +markup.
Profiles, pools and providers can be given by name or ID; times are GMT.

random makes 1-3 markup changes during the day, each on a random profile
(not House) and symbol: up or down by 1-2 points of that symbol. A reduction
stops at zero, so the bid never turns positive or the ask negative. It is
seeded by the date and the latest log entry, so a rerun repeats itself.

Each change is one row in xcore.XCORE_CONFIG_AUDIT_LOG, in the same
transaction as the change:

  Profile 1 Retail, symbol EUR/USD: markup bid -0.00002 -> -0.00003, ask +0.00002 -> +0.00003.
  Profile 4 Toxic, symbol XAU/USD: pool 2 Toxic_FX -> 1 Bank_FX.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from fxgen import auditlog
from fxgen.db import connect

MT4_SERVER = "trade/mt4"
RANDOM_PROFILES = ("Retail", "B2B", "WL", "Toxic")  # House stays at zero markup
CHANGES_PER_DAY = (1, 3)
STEP_POINTS = (1, 2)

LOOKUPS = {
    "profile": "SELECT PROFILE_ID, NAME FROM xcore.XCORE_PROFILES WHERE NAME = %s OR CAST(PROFILE_ID AS CHAR) = %s",
    "pool": "SELECT POOL_ID, NAME FROM xcore.XCORE_LIQUIDITY_POOLS WHERE NAME = %s OR CAST(POOL_ID AS CHAR) = %s",
}


def lookup(cur, kind: str, value: str) -> tuple[int, str]:
    cur.execute(LOOKUPS[kind], (value, value))
    rows = cur.fetchall()
    if len(rows) != 1:
        sys.exit(f"No {kind} named or numbered {value!r}.")
    return rows[0]


def symbol_digits(cur) -> dict[str, int]:
    """Price digits per XCore symbol, from its MT4 symbol: FX without the slash, CFDs by CCY1."""
    cur.execute(
        "SELECT x.SYMBOL, m.DIGITS FROM xcore.XCORE_SYMBOLS x JOIN mt4.MT4_SYMBOLS m "
        "ON m.SERVER = %s AND m.SYMBOL = IF(x.TYPE = 'CFD', x.CCY1, REPLACE(x.SYMBOL, '/', ''))",
        (MT4_SERVER,),
    )
    return dict(cur.fetchall())


def profile_rows(cur, profile_id: int) -> dict[str, tuple[int, Decimal, Decimal]]:
    cur.execute(
        "SELECT XCORE_SYMBOL, POOL_ID, MARKUP_BID, MARKUP_ASK FROM xcore.XCORE_PROFILE_SYMBOLS "
        "WHERE PROFILE_ID = %s ORDER BY XCORE_SYMBOL FOR UPDATE",
        (profile_id,),
    )
    return {sym: (pool, bid, ask) for sym, pool, bid, ask in cur.fetchall()}


def fmt(value: Decimal, digits: int) -> str:
    return f"{0:.{digits}f}" if value == 0 else f"{value:+.{digits}f}"


def set_markup(cur, profile: tuple[int, str], sym: str, row, size: Decimal, digits: int,
               when: datetime) -> str | None:
    _, old_bid, old_ask = row
    new_bid, new_ask = -size, size
    if (new_bid, new_ask) == (old_bid, old_ask):
        return None
    cur.execute(
        "UPDATE xcore.XCORE_PROFILE_SYMBOLS SET MARKUP_BID = %s, MARKUP_ASK = %s "
        "WHERE PROFILE_ID = %s AND XCORE_SYMBOL = %s",
        (new_bid, new_ask, profile[0], sym),
    )
    msg = (f"Profile {profile[0]} {profile[1]}, symbol {sym}: markup bid {fmt(old_bid, digits)} -> "
           f"{fmt(new_bid, digits)}, ask {fmt(old_ask, digits)} -> {fmt(new_ask, digits)}.")
    auditlog.write(cur, when, msg)
    return msg


def set_pool(cur, profile: tuple[int, str], sym: str, row, pool: tuple[int, str], pool_names: dict,
             when: datetime) -> str | None:
    old_pool = row[0]
    if old_pool == pool[0]:
        return None
    cur.execute(
        "UPDATE xcore.XCORE_PROFILE_SYMBOLS SET POOL_ID = %s WHERE PROFILE_ID = %s AND XCORE_SYMBOL = %s",
        (pool[0], profile[0], sym),
    )
    msg = (f"Profile {profile[0]} {profile[1]}, symbol {sym}: pool {old_pool} {pool_names[old_pool]} -> "
           f"{pool[0]} {pool[1]}.")
    auditlog.write(cur, when, msg)
    return msg


def run_set(cur, args) -> list[str]:
    if args.markup is None and args.pool is None:
        sys.exit("Give --markup, --pool, or both.")
    when = auditlog.change_time(args.time)
    auditlog.check_order(cur, when)
    profile = lookup(cur, "profile", args.profile)
    rows = profile_rows(cur, profile[0])
    unknown = [s for s in args.symbol if s not in rows]
    if unknown:
        sys.exit(f"Not in profile {profile[1]}: {', '.join(unknown)}")
    digits = symbol_digits(cur)
    pool = lookup(cur, "pool", args.pool) if args.pool else None
    cur.execute("SELECT POOL_ID, NAME FROM xcore.XCORE_LIQUIDITY_POOLS")
    pool_names = dict(cur.fetchall())

    messages = []
    for sym in args.symbol:
        if args.markup is not None:
            size = Decimal(args.markup)
            if size < 0 or size != size.quantize(Decimal(1).scaleb(-digits[sym])):
                sys.exit(f"--markup {args.markup} must be zero or more, with at most {digits[sym]} decimals for {sym}.")
            messages.append(set_markup(cur, profile, sym, rows[sym], size, digits[sym], when))
        if pool:
            messages.append(set_pool(cur, profile, sym, rows[sym], pool, pool_names, when))
    return [m for m in messages if m]


def run_random(cur, day: date) -> list[str]:
    last_id, last_time = auditlog.latest(cur)
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    if last_time is not None:
        start = max(start, last_time)
    if start >= end:
        sys.exit(f"The log already has entries after {day}; random changes must stay in time order.")

    rng = random.Random(f"{day}:{last_id}")
    digits = symbol_digits(cur)
    span_ms = int((end - start).total_seconds() * 1000)
    times = sorted(start + timedelta(milliseconds=rng.randrange(span_ms))
                   for _ in range(rng.randint(*CHANGES_PER_DAY)))

    messages = []
    for when in times:
        profile = lookup(cur, "profile", rng.choice(RANDOM_PROFILES))
        rows = profile_rows(cur, profile[0])
        sym = rng.choice(sorted(rows))
        size = rows[sym][2]
        step = rng.randint(*STEP_POINTS) * Decimal(1).scaleb(-digits[sym])
        up = size == 0 or rng.random() < 0.5
        new_size = size + step if up else max(Decimal(0), size - step)
        messages.append(set_markup(cur, profile, sym, rows[sym], new_size, digits[sym], when))
    return [m for m in messages if m]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    p_set = sub.add_parser("set", help="set markup and/or pool for symbols in a profile")
    p_set.add_argument("--profile", required=True, help="profile name or ID")
    p_set.add_argument("--symbol", nargs="+", required=True, help="XCore symbols to change")
    p_set.add_argument("--markup", help="markup size in price, e.g. 0.00003")
    p_set.add_argument("--pool", help="pool name or ID")
    p_set.add_argument("--time", type=datetime.fromisoformat, help="change time, GMT (default: now)")
    p_rand = sub.add_parser("random", help="make the day's random markup changes")
    p_rand.add_argument("--date", type=date.fromisoformat, default=date.today(), help="GMT day (default: today)")
    args = parser.parse_args()

    conn = connect()
    cur = conn.cursor()
    messages = run_set(cur, args) if args.action == "set" else run_random(cur, args.date)
    conn.commit()
    conn.close()
    for m in messages:
        print(m)
    print(f"{len(messages)} change(s) logged.")


if __name__ == "__main__":
    main()
