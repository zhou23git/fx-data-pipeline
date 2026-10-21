"""XCore configuration: the initial tables, the changes made during the
simulated period, and the audit log those changes leave behind.

The generator applies whichever configuration was live at each order's
timestamp. What gets exported is only the configuration as of the end of the
period plus the audit log -- rebuilding the configuration at order time is the
learner's job.
"""
from __future__ import annotations

import bisect
import copy
import fnmatch
import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from fxgen.reference import PROVIDERS, SERVERS, SYMBOLS, provider_symbol

Tables = dict[str, dict[str, dict]]

PRIMARY_KEYS = {
    "SYMBOL": ("XCORE_SYMBOL",),
    "PROVIDER": ("PROVIDER_ID",),
    "PROVIDER_SYMBOL_MAP": ("PROVIDER_ID", "PROVIDER_SYMBOL"),
    "LIQUIDITY_POOL": ("POOL_ID",),
    "LIQUIDITY_POOL_MEMBER": ("MEMBER_ID",),
    "PROFILE": ("PROFILE_ID",),
    "PROFILE_MARKUP": ("PROFILE_ID", "XCORE_SYMBOL", "BAND_NO"),
    "PROFILE_COMMISSION": ("PROFILE_ID", "XCORE_SYMBOL"),
    "CONNECTOR": ("CONNECTOR_ID",),
    "CONNECTOR_SYMBOL_MAP": ("CONNECTOR_ID", "CLIENT_SYMBOL"),
    "CONNECTOR_ACCOUNT": ("ACCOUNT_ID",),
    "CONNECTOR_STREAM": ("STREAM_ID",),
    "CONNECTOR_ACCOUNT_SETTING": ("ACCOUNT_ID", "XCORE_SYMBOL"),
    "ROUTING_RULE": ("RULE_ID",),
    "GIVEUP": ("GIVEUP_ID",),
}


def record_id(table: str, row: dict) -> str:
    return "|".join(str(row[k]) for k in PRIMARY_KEYS[table])


# Markup bands: (max qty in lots, 0 = no limit) -> markup pips per side.
RETAIL_BANDS = [(10, 0.2), (50, 0.3), (0, 0.5)]
PRIME_BANDS = [(50, 0.05), (200, 0.1), (0, 0.2)]
METAL_BAND_PIPS = {"POOL_RETAIL": [15, 25, 40], "POOL_PRIME": [5, 8, 12]}


def initial_tables() -> Tables:
    t: Tables = {name: {} for name in PRIMARY_KEYS}

    def add(table: str, **row):
        t[table][record_id(table, row)] = row

    for s in SYMBOLS.values():
        add("SYMBOL", XCORE_SYMBOL=s.name, BASE_CCY=s.base, QUOTE_CCY=s.quote, DIGITS=s.digits + 1,
            CONTRACT_SIZE=s.contract, MIN_QTY=s.contract / 100, QTY_STEP=s.contract / 100)

    for n, p in enumerate(PROVIDERS.values()):
        add("PROVIDER", PROVIDER_ID=p.provider_id, NAME=p.name, EXECUTION_TYPE=p.execution_type,
            FIX_HOST="" if p.provider_id == "INTERNAL" else f"fix{n + 1}.{p.provider_id.lower()}.net",
            FIX_PORT=0 if p.provider_id == "INTERNAL" else 9870 + n,
            SENDER_COMP_ID="" if p.provider_id == "INTERNAL" else "FXCO_XC",
            TARGET_COMP_ID="" if p.provider_id == "INTERNAL" else p.provider_id.replace("LP_", ""),
            ENABLED=1)
        for sym in p.symbols:
            add("PROVIDER_SYMBOL_MAP", PROVIDER_ID=p.provider_id,
                PROVIDER_SYMBOL=provider_symbol(p.provider_id, sym), XCORE_SYMBOL=sym,
                QTY_MULTIPLIER=p.qty_multiplier.get(sym, 1))

    member = 0
    for pool, name in (("POOL_RETAIL", "Retail pool"), ("POOL_PRIME", "Prime pool")):
        add("LIQUIDITY_POOL", POOL_ID=pool, NAME=name)
        for sym in SYMBOLS:
            providers = ["LP_BANKA", "LP_BANKB", "LP_NBC"] if SYMBOLS[sym].asset == "FX" else ["LP_METALS"]
            if pool == "POOL_PRIME" and sym == "XAUUSD":
                providers = ["LP_METALS", "LP_BANKB"]
            for prio, pid in enumerate(providers, start=1):
                member += 1
                add("LIQUIDITY_POOL_MEMBER", MEMBER_ID=f"M{member:03d}", POOL_ID=pool,
                    XCORE_SYMBOL=sym, PROVIDER_ID=pid, SESSION="*", PRIORITY=prio, ENABLED=1)

    for profile, ptype, name in (
        ("LP_RETAIL", "LIQUIDITY", "Retail markup"),
        ("LP_PRIME", "LIQUIDITY", "Prime markup"),
        ("COMM_PRIME", "COMMISSION", "Prime commission"),
    ):
        add("PROFILE", PROFILE_ID=profile, NAME=name, TYPE=ptype)
    for profile, bands, pool in (("LP_RETAIL", RETAIL_BANDS, "POOL_RETAIL"),
                                 ("LP_PRIME", PRIME_BANDS, "POOL_PRIME")):
        for sym, s in SYMBOLS.items():
            for band_no, (max_lots, pips) in enumerate(bands, start=1):
                if s.asset == "METAL":
                    pips = METAL_BAND_PIPS[pool][band_no - 1]
                add("PROFILE_MARKUP", PROFILE_ID=profile, XCORE_SYMBOL=sym, BAND_NO=band_no,
                    MAX_QTY=max_lots * s.contract, MARKUP_BID_PIPS=pips, MARKUP_ASK_PIPS=pips)
    add("PROFILE_COMMISSION", PROFILE_ID="COMM_PRIME", XCORE_SYMBOL="*",
        COMMISSION_TYPE="PER_MILLION_USD", VALUE=5.0)

    for server in SERVERS.values():
        tag = server.name.split("_")[1]  # RETAIL / PRIME
        conn = server.connector_id
        add("CONNECTOR", CONNECTOR_ID=conn, NAME=server.name.lower(), TYPE="MT4_BRIDGE",
            HOST=f"{server.name.lower().replace('_', '-')}.fxco.local:443", MT4_SERVER=server.name, ENABLED=1)
        for sym in SYMBOLS:
            add("CONNECTOR_SYMBOL_MAP", CONNECTOR_ID=conn, CLIENT_SYMBOL=sym + server.suffix, XCORE_SYMBOL=sym)
        add("CONNECTOR_ACCOUNT", ACCOUNT_ID=f"ACC_{tag}", CONNECTOR_ID=conn, NAME=f"{tag.lower()}_trading",
            POOL_ID=f"POOL_{tag}", LIQUIDITY_PROFILE_ID=f"LP_{tag}",
            COMMISSION_PROFILE_ID="COMM_PRIME" if tag == "PRIME" else "", ENABLED=1)
        add("CONNECTOR_STREAM", STREAM_ID=f"STR_{tag}", CONNECTOR_ID=conn, NAME=f"{tag.lower()}_pricing",
            POOL_ID=f"POOL_{tag}", LIQUIDITY_PROFILE_ID=f"LP_{tag}", ENABLED=1)
        for sym, s in SYMBOLS.items():
            add("CONNECTOR_ACCOUNT_SETTING", ACCOUNT_ID=f"ACC_{tag}", XCORE_SYMBOL=sym,
                EXECUTION_MODE="SWEEP", FOK_THRESHOLD_QTY=50 * s.contract, MAX_ORDER_QTY=500 * s.contract)

    # Routing: lowest PRIORITY wins. MAX_QTY 0 = no limit.
    rules = [
        ("R100", 100, "CON_MT4_RETAIL", "*", "real\\*\\std", "*", "!XAUUSD,*", 0, 20 * 100_000, "B"),
        ("R110", 110, "CON_MT4_RETAIL", "*", "real\\*\\std", "*", "XAUUSD", 0, 2 * 100, "B"),
        ("R120", 120, "CON_MT4_RETAIL", "*", "real\\*\\raw", "*", "*", 0, 0, "A"),
        ("R200", 200, "CON_MT4_PRIME", "*", "*", "*", "*", 0, 0, "A"),
        ("R999", 999, "*", "*", "*", "*", "*", 0, 0, "A"),
    ]
    for rid, prio, conn, acct, group, client, sym, mn, mx, book in rules:
        add("ROUTING_RULE", RULE_ID=rid, PRIORITY=prio, CONNECTOR=conn, ACCOUNT=acct, MT4_GROUP=group,
            CLIENT=client, XCORE_SYMBOL=sym, MIN_QTY=mn, MAX_QTY=mx, BOOK=book, ENABLED=1)

    giveups = [
        ("G01", 10, "CON_MT4_RETAIL", "*", "*", "*", "*", "all",
         "login=70000,markups=none,gu_markup=0,comment=RETAIL_NET"),
        ("G02", 10, "CON_MT4_PRIME", "*", "*", "*", "*", "all",
         "login=70001,markups=none,gu_markup=0,comment=B2B_NET"),
        ("G03", 20, "CON_MT4_RETAIL", "*", "real\\uk\\*", "!XAUUSD,*", "*", "a_only",
         "login=70100,markups=xcore,gu_markup=0,comment=UK_MARKUP"),
        ("G04", 20, "CON_MT4_RETAIL", "*", "real\\uk\\*", "XAUUSD", "*", "all",
         "login=70100,markups=none,gu_markup=20,comment=UK_MARKUP_GOLD"),
        ("G05", 30, "CON_MT4_RETAIL", "*", "real\\svg\\*", "*", "*", "all",
         "login=70200,markups=all,gu_markup=0,comment=SVG_MARKUP"),
        ("G06", 15, "CON_MT4_RETAIL", "*", "real\\svg\\raw", "*", "!INTERNAL,*", "all",
         "login=70200,markups=xcore,gu_markup=0.1,comment=SVG_MARKUP_RAW"),
    ]
    for gid, prio, conn, acct, group, sym, prov, book, value in giveups:
        add("GIVEUP", GIVEUP_ID=gid, PRIORITY=prio, CONNECTOR=conn, ACCOUNT=acct, MT4_GROUP=group,
            XCORE_SYMBOL=sym, PROVIDER=prov, BOOK=book, VALUE=value, ENABLED=1)
    return t


# ---------------------------------------------------------------------------
# Changes during the period
# ---------------------------------------------------------------------------

@dataclass
class Edit:
    table: str
    action: str           # INSERT / UPDATE
    rid: str = ""
    field: str = ""
    value: object = None
    row: dict | None = None


@dataclass
class Commit:
    time: datetime
    user: str
    edits: list[Edit]
    note: str             # for the answer key, never exported


def _when(start: datetime, end: datetime, frac: float, at: time = time(8, 15)) -> datetime:
    d = (start + (end - start) * frac).date()
    while d.weekday() >= 5:  # dealing desk changes happen on weekdays
        d += timedelta(days=1)
    return datetime.combine(d, at)


def scheduled_commits(start: datetime, end: datetime, toxic_logins: list[int]) -> list[Commit]:
    c: list[Commit] = []

    def up(table, rid, field, value):
        return Edit(table, "UPDATE", rid, field, value)

    c.append(Commit(_when(start, end, 0.12), "dealer_mike", [
        up("PROFILE_MARKUP", "LP_RETAIL|EURUSD|1", "MARKUP_BID_PIPS", 0.3),
        up("PROFILE_MARKUP", "LP_RETAIL|EURUSD|1", "MARKUP_ASK_PIPS", 0.3),
    ], "Retail EURUSD band-1 markup 0.2 -> 0.3 pips"))

    c.append(Commit(_when(start, end, 0.20, time(10, 2)), "ops_anna", [
        Edit("LIQUIDITY_POOL_MEMBER", "INSERT", row=dict(
            MEMBER_ID="M101", POOL_ID="POOL_RETAIL", XCORE_SYMBOL="XAUUSD", PROVIDER_ID="LP_BANKB",
            SESSION="*", PRIORITY=2, ENABLED=1)),
    ], "Bank B added to the retail gold pool"))

    c.append(Commit(_when(start, end, 0.30, time(14, 40)), "jzhou", [
        Edit("GIVEUP", "INSERT", row=dict(
            GIVEUP_ID="G07", PRIORITY=40, CONNECTOR="CON_MT4_PRIME", ACCOUNT="*", MT4_GROUP="*",
            XCORE_SYMBOL="*", PROVIDER="LP_NBC", BOOK="a_only",
            VALUE="login=70300,markups=none,gu_markup=0,comment=NBC_DROP", ENABLED=1)),
    ], "Drop copy of prime flow filled by NonBank C, for LP statement reconciliation"))

    v2_rows = []
    for sym, s in SYMBOLS.items():
        for band_no, (max_lots, pips) in enumerate(RETAIL_BANDS, start=1):
            if s.asset == "METAL":
                pips = METAL_BAND_PIPS["POOL_RETAIL"][band_no - 1]
            elif sym == "EURUSD" and band_no == 1:
                pips = 0.3
            if s.asset == "FX" and band_no == 1:
                pips = round(pips + 0.1, 2)
            v2_rows.append(Edit("PROFILE_MARKUP", "INSERT", row=dict(
                PROFILE_ID="LP_RETAIL_V2", XCORE_SYMBOL=sym, BAND_NO=band_no, MAX_QTY=max_lots * s.contract,
                MARKUP_BID_PIPS=pips, MARKUP_ASK_PIPS=pips)))
    c.append(Commit(_when(start, end, 0.38, time(7, 30)), "dealer_mike", [
        Edit("PROFILE", "INSERT", row=dict(PROFILE_ID="LP_RETAIL_V2", NAME="Retail markup v2", TYPE="LIQUIDITY")),
        *v2_rows,
        up("CONNECTOR_ACCOUNT", "ACC_RETAIL", "LIQUIDITY_PROFILE_ID", "LP_RETAIL_V2"),
    ], "Retail account moved to LP_RETAIL_V2 (+0.1 pip band 1 FX). Stream NOT moved yet: fills worse than quotes"))

    c.append(Commit(_when(start, end, 0.42, time(9, 5)), "dealer_mike", [
        up("CONNECTOR_STREAM", "STR_RETAIL", "LIQUIDITY_PROFILE_ID", "LP_RETAIL_V2"),
    ], "Retail stream moved to LP_RETAIL_V2: quote/fill mismatch window closed"))

    c.append(Commit(_when(start, end, 0.47, time(11, 20)), "risk_omar", [
        Edit("ROUTING_RULE", "INSERT", row=dict(
            RULE_ID="R050", PRIORITY=50, CONNECTOR="CON_MT4_RETAIL", ACCOUNT="*", MT4_GROUP="*",
            CLIENT=",".join(str(x) for x in toxic_logins) or "none", XCORE_SYMBOL="*",
            MIN_QTY=0, MAX_QTY=0, BOOK="A", ENABLED=1)),
    ], "Toxic scalpers moved to A-book"))

    nbc_members = "NBC_MEMBERS"  # resolved at apply time
    c.append(Commit(_when(start, end, 0.50, time(13, 0)), "ops_anna",
                    [Edit("LIQUIDITY_POOL_MEMBER", "UPDATE", nbc_members, "ENABLED", 0)],
                    "NonBank C disabled in every pool (connectivity incident)"))
    c.append(Commit(_when(start, end, 0.52, time(8, 45)), "ops_anna",
                    [Edit("LIQUIDITY_POOL_MEMBER", "UPDATE", nbc_members, "ENABLED", 1)],
                    "NonBank C re-enabled"))

    c.append(Commit(_when(start, end, 0.60, time(15, 10)), "jzhou", [
        up("GIVEUP", "G05", "VALUE", "login=70200,markups=all,gu_markup=0.1,comment=SVG_MARKUP"),
    ], "SVG markup coverage takes an extra 0.1 pip giveup markup"))

    c.append(Commit(_when(start, end, 0.70, time(6, 50)), "dealer_mike", [
        up("CONNECTOR_ACCOUNT_SETTING", f"ACC_PRIME|{sym}", "FOK_THRESHOLD_QTY", 20 * s.contract)
        for sym, s in SYMBOLS.items()
    ], "Prime single-FOK threshold lowered from 50 to 20 lots"))

    typo_at = _when(start, end, 0.77, time(13, 52))
    c.append(Commit(typo_at, "dealer_mike", [
        up("PROFILE_MARKUP", "LP_RETAIL_V2|XAUUSD|1", "MARKUP_ASK_PIPS", 150),
    ], "FAT FINGER: retail gold ask markup 15 -> 150 pips"))
    c.append(Commit(typo_at + timedelta(minutes=7), "dealer_mike", [
        up("PROFILE_MARKUP", "LP_RETAIL_V2|XAUUSD|1", "MARKUP_ASK_PIPS", 15),
    ], "Fat finger reverted"))

    c.append(Commit(_when(start, end, 0.85, time(9, 30)), "jzhou", [
        up("GIVEUP", "G03", "ENABLED", 0),
    ], "UK A-book FX markup giveup switched off; UK coverage positions opened before stay open"))
    return [x for x in c if start <= x.time < end]


# ---------------------------------------------------------------------------
# Applying changes and querying a configuration
# ---------------------------------------------------------------------------

@dataclass
class AuditRow:
    time: datetime
    user: str
    table: str
    rid: str
    action: str
    field: str
    old: str
    new: str


def _fmt(v) -> str:
    return "" if v is None else str(v)


def apply_commit(tables: Tables, commit: Commit) -> list[AuditRow]:
    log = []
    for e in commit.edits:
        if e.action == "INSERT":
            rid = record_id(e.table, e.row)
            tables[e.table][rid] = dict(e.row)
            log.append(AuditRow(commit.time, commit.user, e.table, rid, "INSERT", "*", "",
                                json.dumps(e.row, separators=(",", ":"))))
            continue
        if e.rid == "NBC_MEMBERS":
            rids = [k for k, r in tables[e.table].items() if r["PROVIDER_ID"] == "LP_NBC"]
        else:
            rids = [e.rid]
        for rid in rids:
            row = tables[e.table][rid]
            old = row[e.field]
            row[e.field] = e.value
            log.append(AuditRow(commit.time, commit.user, e.table, rid, "UPDATE", e.field, _fmt(old), _fmt(e.value)))
    return log


def mask_match(pattern: str, value: str) -> bool:
    """Comma-separated masks with '*' wildcards and '!' negation; the first
    token that matches decides. "!XAUUSD,*" = everything except XAUUSD."""
    for token in pattern.split(","):
        token = token.strip()
        negate = token.startswith("!")
        if negate:
            token = token[1:]
        if fnmatch.fnmatchcase(value, token):
            return not negate
    return False


def parse_value(value: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in value.split(","))


class Config:
    """One point-in-time configuration with lookup indexes."""

    def __init__(self, tables: Tables):
        self.tables = tables
        self.client_symbol = {(r["CONNECTOR_ID"], r["CLIENT_SYMBOL"]): r["XCORE_SYMBOL"]
                              for r in tables["CONNECTOR_SYMBOL_MAP"].values()}
        self.account = {r["CONNECTOR_ID"]: r for r in tables["CONNECTOR_ACCOUNT"].values()}
        self.stream = {r["CONNECTOR_ID"]: r for r in tables["CONNECTOR_STREAM"].values()}
        self.pool: dict[tuple[str, str], list[str]] = {}
        for r in sorted(tables["LIQUIDITY_POOL_MEMBER"].values(), key=lambda r: (r["PRIORITY"], r["MEMBER_ID"])):
            if r["ENABLED"] and tables["PROVIDER"][r["PROVIDER_ID"]]["ENABLED"]:
                self.pool.setdefault((r["POOL_ID"], r["XCORE_SYMBOL"]), []).append(r["PROVIDER_ID"])
        self.bands: dict[tuple[str, str], list[dict]] = {}
        for r in sorted(tables["PROFILE_MARKUP"].values(), key=lambda r: r["BAND_NO"]):
            self.bands.setdefault((r["PROFILE_ID"], r["XCORE_SYMBOL"]), []).append(r)
        self.setting = {(r["ACCOUNT_ID"], r["XCORE_SYMBOL"]): r for r in tables["CONNECTOR_ACCOUNT_SETTING"].values()}
        self.commission = {(r["PROFILE_ID"], r["XCORE_SYMBOL"]): r for r in tables["PROFILE_COMMISSION"].values()}
        self.routing = sorted((r for r in tables["ROUTING_RULE"].values() if r["ENABLED"]),
                              key=lambda r: (r["PRIORITY"], r["RULE_ID"]))
        self.giveups = sorted((r for r in tables["GIVEUP"].values() if r["ENABLED"]),
                              key=lambda r: (r["PRIORITY"], r["GIVEUP_ID"]))
        self.provider_symbol = {(r["PROVIDER_ID"], r["XCORE_SYMBOL"]): r
                                for r in tables["PROVIDER_SYMBOL_MAP"].values()}

    def markup(self, profile: str, symbol: str, qty: float) -> tuple[dict, int]:
        bands = self.bands[(profile, symbol)]
        for b in bands:
            if b["MAX_QTY"] == 0 or qty <= b["MAX_QTY"]:
                return b, b["BAND_NO"]
        return bands[-1], bands[-1]["BAND_NO"]

    def route(self, connector: str, account: str, group: str, login: int, symbol: str, qty: float) -> dict:
        for r in self.routing:
            if (mask_match(r["CONNECTOR"], connector) and mask_match(r["ACCOUNT"], account)
                    and mask_match(r["MT4_GROUP"], group) and mask_match(r["CLIENT"], str(login))
                    and mask_match(r["XCORE_SYMBOL"], symbol) and qty >= r["MIN_QTY"]
                    and (r["MAX_QTY"] == 0 or qty <= r["MAX_QTY"])):
                return r
        raise LookupError("no routing rule matched")

    def giveups_for(self, connector: str, account: str, group: str, symbol: str,
                    provider: str, book: str) -> list[tuple[dict, dict]]:
        chosen: dict[str, tuple[dict, dict]] = {}
        for r in self.giveups:
            if r["BOOK"] == "a_only" and book != "A" or r["BOOK"] == "b_only" and book != "B":
                continue
            if not (mask_match(r["CONNECTOR"], connector) and mask_match(r["ACCOUNT"], account)
                    and mask_match(r["MT4_GROUP"], group) and mask_match(r["XCORE_SYMBOL"], symbol)
                    and mask_match(r["PROVIDER"], provider)):
                continue
            value = parse_value(r["VALUE"])
            chosen.setdefault(value["login"], (r, value))  # first (lowest priority) per login wins
        return list(chosen.values())


class ConfigTimeline:
    def __init__(self, commits: list[Commit]):
        tables = initial_tables()
        self.times = [datetime.min]
        self.configs = [Config(copy.deepcopy(tables))]
        self.audit: list[AuditRow] = []
        for commit in sorted(commits, key=lambda c: c.time):
            self.audit.extend(apply_commit(tables, commit))
            self.times.append(commit.time)
            self.configs.append(Config(copy.deepcopy(tables)))
        self.final = tables
        self.commits = commits

    def at(self, t: datetime) -> tuple[Config, int]:
        i = bisect.bisect_right(self.times, t) - 1
        return self.configs[i], i
