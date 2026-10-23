"""Change XCore liquidity pool settings and log each change.

  python -m fxgen.pools drop --pool Bank_FX --provider BankB
  python -m fxgen.pools add --pool Bank_FX --provider BankB --symbol EUR/USD GBP/USD --time "2026-10-23 14:05:00"
  python -m fxgen.pools assign --account Toxic --pool Toxic_FX

add/drop put an existing provider into, or take it out of, a pool; without
--symbol, every symbol in the pool changes. assign sets the pool a connector
account trades from; --connector is only needed when the account name is on
more than one connector. Pools, providers, connectors and accounts can be
given by name or ID. --time is the change time in GMT (default: now), and may
not be earlier than the latest log entry. Each change is one row in
xcore.XCORE_CONFIG_AUDIT_LOG, in the same transaction as the change:

  Liquidity pool 1 Bank_FX, symbol EUR/USD: removed provider 3 BankB. Providers 1,3 -> 1.
  Connector trade/mt4, account 4 Toxic: pool 1 Bank_FX -> 2 Toxic_FX.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from fxgen import auditlog
from fxgen.db import connect

LOOKUPS = {
    "pool": "SELECT POOL_ID, NAME FROM xcore.XCORE_LIQUIDITY_POOLS WHERE NAME = %s OR CAST(POOL_ID AS CHAR) = %s",
    "provider": "SELECT PROVIDER_ID, NAME FROM xcore.XCORE_PROVIDERS WHERE NAME = %s OR CAST(PROVIDER_ID AS CHAR) = %s",
}


def lookup(cur, kind: str, value: str) -> tuple[int, str]:
    cur.execute(LOOKUPS[kind], (value, value))
    rows = cur.fetchall()
    if len(rows) != 1:
        sys.exit(f"No {kind} named or numbered {value!r}.")
    return rows[0]


def to_csv(ids: list[int]) -> str:
    return ",".join(str(i) for i in sorted(ids))


def change(cur, action: str, pool: str, provider: str, symbols: list[str] | None,
           when: datetime) -> list[str]:
    """Apply the change and write its log rows; the caller commits."""
    pool_id, pool_name = lookup(cur, "pool", pool)
    prov_id, prov_name = lookup(cur, "provider", provider)

    auditlog.check_order(cur, when)

    cur.execute(
        "SELECT XCORE_SYMBOL, PROVIDER_ID FROM xcore.XCORE_LIQUIDITY_POOL_PROVIDERS "
        "WHERE POOL_ID = %s ORDER BY XCORE_SYMBOL FOR UPDATE",
        (pool_id,),
    )
    current = dict(cur.fetchall())
    if symbols:
        unknown = [s for s in symbols if s not in current]
        if unknown:
            sys.exit(f"Not in pool {pool_name}: {', '.join(unknown)}")
    targets = symbols or list(current)

    messages = []
    for sym in targets:
        old = [int(x) for x in current[sym].split(",")]
        if action == "add":
            if prov_id in old:
                print(f"Skipped {sym}: already has provider {prov_id} {prov_name}.", file=sys.stderr)
                continue
            new, verb = old + [prov_id], "added"
        else:
            if prov_id not in old:
                print(f"Skipped {sym}: provider {prov_id} {prov_name} isn't in it.", file=sys.stderr)
                continue
            if len(old) == 1:
                print(f"Skipped {sym}: dropping {prov_name} would leave no providers.", file=sys.stderr)
                continue
            new, verb = [p for p in old if p != prov_id], "removed"

        old_csv, new_csv = to_csv(old), to_csv(new)
        msg = (f"Liquidity pool {pool_id} {pool_name}, symbol {sym}: {verb} provider "
               f"{prov_id} {prov_name}. Providers {old_csv} -> {new_csv}.")
        cur.execute(
            "UPDATE xcore.XCORE_LIQUIDITY_POOL_PROVIDERS SET PROVIDER_ID = %s "
            "WHERE POOL_ID = %s AND XCORE_SYMBOL = %s",
            (new_csv, pool_id, sym),
        )
        auditlog.write(cur, when, msg)
        messages.append(msg)
    return messages


def assign(cur, account: str, pool: str, connector: str | None, when: datetime) -> list[str]:
    """Point a connector account at a pool and log it; the caller commits."""
    pool_id, pool_name = lookup(cur, "pool", pool)
    auditlog.check_order(cur, when)

    sql = ("SELECT a.ACCOUNT_ID, a.NAME, c.NAME, a.POOL_ID, l.NAME FROM xcore.XCORE_CONNECTOR_ACCOUNTS a "
           "JOIN xcore.XCORE_CONNECTORS c USING (CONNECTOR_ID) "
           "JOIN xcore.XCORE_LIQUIDITY_POOLS l ON l.POOL_ID = a.POOL_ID "
           "WHERE (a.NAME = %s OR CAST(a.ACCOUNT_ID AS CHAR) = %s)")
    params = [account, account]
    if connector:
        sql += " AND (c.NAME = %s OR CAST(c.CONNECTOR_ID AS CHAR) = %s)"
        params += [connector, connector]
    cur.execute(sql + " FOR UPDATE", params)
    rows = cur.fetchall()
    if not rows:
        sys.exit(f"No connector account named or numbered {account!r}" + (f" on {connector!r}." if connector else "."))
    if len(rows) > 1:
        sys.exit(f"Account {account!r} is on several connectors ({', '.join(r[2] for r in rows)}); give --connector.")
    acc_id, acc_name, con_name, old_pool_id, old_pool_name = rows[0]
    if old_pool_id == pool_id:
        print(f"Skipped: account {acc_name} already trades from {pool_name}.", file=sys.stderr)
        return []

    cur.execute("UPDATE xcore.XCORE_CONNECTOR_ACCOUNTS SET POOL_ID = %s WHERE ACCOUNT_ID = %s", (pool_id, acc_id))
    msg = (f"Connector {con_name}, account {acc_id} {acc_name}: pool {old_pool_id} {old_pool_name} -> "
           f"{pool_id} {pool_name}.")
    auditlog.write(cur, when, msg)
    return [msg]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("add", "drop"):
        p = sub.add_parser(action, help=f"{action} a provider in a pool")
        p.add_argument("--pool", required=True, help="pool name or ID")
        p.add_argument("--provider", required=True, help="provider name or ID")
        p.add_argument("--symbol", nargs="+", help="XCore symbols to change (default: all in the pool)")
        p.add_argument("--time", type=datetime.fromisoformat, help="change time, GMT (default: now)")
    p = sub.add_parser("assign", help="set the pool a connector account trades from")
    p.add_argument("--account", required=True, help="connector account name or ID")
    p.add_argument("--pool", required=True, help="pool name or ID")
    p.add_argument("--connector", help="connector name or ID, if the account name is ambiguous")
    p.add_argument("--time", type=datetime.fromisoformat, help="change time, GMT (default: now)")
    args = parser.parse_args()

    when = auditlog.change_time(args.time)

    conn = connect()
    cur = conn.cursor()
    if args.action == "assign":
        messages = assign(cur, args.account, args.pool, args.connector, when)
    else:
        messages = change(cur, args.action, args.pool, args.provider, args.symbol, when)
    conn.commit()
    conn.close()
    for m in messages:
        print(m)
    print(f"{len(messages)} change(s) logged at {when}.")


if __name__ == "__main__":
    main()
