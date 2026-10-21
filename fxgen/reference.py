"""Static reference data: instruments, liquidity providers, MT4 servers and
groups, coverage accounts, and client behaviour profiles."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Symbol:
    name: str
    base: str
    quote: str
    digits: int
    pip: float
    contract: float      # units per lot
    start: float         # opening mid; 0 for crosses derived from drivers
    vol: float           # annualised volatility (drivers only)
    spread_pips: float   # typical interbank spread
    swap_long: float     # USD per lot per night
    swap_short: float
    popularity: int
    asset: str           # FX or METAL


SYMBOLS: dict[str, Symbol] = {s.name: s for s in [
    Symbol("EURUSD", "EUR", "USD", 5, 0.0001, 100_000, 1.0850, 0.07, 0.2, -7.0, 2.0, 25, "FX"),
    Symbol("GBPUSD", "GBP", "USD", 5, 0.0001, 100_000, 1.2700, 0.08, 0.4, -5.0, 0.5, 14, "FX"),
    Symbol("USDJPY", "USD", "JPY", 3, 0.01, 100_000, 147.50, 0.10, 0.3, 12.0, -25.0, 12, "FX"),
    Symbol("AUDUSD", "AUD", "USD", 5, 0.0001, 100_000, 0.6600, 0.10, 0.4, -3.0, -1.0, 6, "FX"),
    Symbol("USDCAD", "USD", "CAD", 5, 0.0001, 100_000, 1.3600, 0.06, 0.5, 2.0, -9.0, 5, "FX"),
    Symbol("USDCHF", "USD", "CHF", 5, 0.0001, 100_000, 0.8800, 0.07, 0.5, 6.0, -14.0, 3, "FX"),
    Symbol("XAUUSD", "XAU", "USD", 2, 0.01, 100, 2350.00, 0.15, 12.0, -45.0, 20.0, 18, "METAL"),
    Symbol("EURGBP", "EUR", "GBP", 5, 0.0001, 100_000, 0.0, 0.0, 0.6, -6.0, 1.0, 4, "FX"),
    Symbol("EURJPY", "EUR", "JPY", 3, 0.01, 100_000, 0.0, 0.0, 0.8, 10.0, -22.0, 4, "FX"),
    Symbol("GBPJPY", "GBP", "JPY", 3, 0.01, 100_000, 0.0, 0.0, 1.2, 14.0, -28.0, 5, "FX"),
]}

# Crosses are derived from the drivers so the price set stays arbitrage-free.
CROSSES = {
    "EURGBP": ("EURUSD", "/", "GBPUSD"),
    "EURJPY": ("EURUSD", "*", "USDJPY"),
    "GBPJPY": ("GBPUSD", "*", "USDJPY"),
}


@dataclass(frozen=True)
class Provider:
    provider_id: str
    name: str
    execution_type: str      # SWEEP: layered book; FULL_AMOUNT: one price for any size
    spread_mult: float
    reject_prob: float       # last-look rejection rate
    symbol_format: str
    symbols: tuple[str, ...]
    qty_multiplier: dict     # provider quantity unit, per symbol (default 1 = base units)


ALL = tuple(SYMBOLS)
FX_ONLY = tuple(s for s in SYMBOLS if SYMBOLS[s].asset == "FX")

PROVIDERS: dict[str, Provider] = {p.provider_id: p for p in [
    Provider("LP_BANKA", "Bank A", "SWEEP", 1.00, 0.004, "{base}/{quote}", FX_ONLY, {}),
    Provider("LP_BANKB", "Bank B", "SWEEP", 1.15, 0.004, "{base}{quote}.ecn", ALL, {}),
    Provider("LP_NBC", "NonBank C", "FULL_AMOUNT", 0.85, 0.03, "{base}{quote}", FX_ONLY, {}),
    # Metals D quotes gold in 100 oz lots, so its leg quantities are 1/100 of XCore's.
    Provider("LP_METALS", "Metals D", "SWEEP", 0.90, 0.01, "{base}/{quote}.spot", ("XAUUSD",),
             {"XAUUSD": 100}),
    Provider("INTERNAL", "B-Book", "INTERNAL", 0.0, 0.0, "{base}{quote}", ALL, {}),
]}


def provider_symbol(provider_id: str, xcore_symbol: str) -> str:
    s = SYMBOLS[xcore_symbol]
    return PROVIDERS[provider_id].symbol_format.format(base=s.base, quote=s.quote)


@dataclass(frozen=True)
class Mt4Server:
    name: str
    connector_id: str
    suffix: str
    login_start: int
    ticket_start: int


SERVERS: dict[str, Mt4Server] = {s.name: s for s in [
    Mt4Server("MT4_RETAIL", "CON_MT4_RETAIL", ".retail", 100_000, 3_000_000),
    Mt4Server("MT4_PRIME", "CON_MT4_PRIME", ".prime", 500_000, 6_000_000),
]}


@dataclass(frozen=True)
class Mt4Group:
    server: str
    group: str
    entity: str          # UK, SVG, or B2B
    kind: str            # std, raw, b2b, coverage
    markup_fx: float     # MT4 spread difference, pips, total across bid+ask
    markup_metal: float
    commission: float    # USD per lot, round turn, charged at open
    leverage: int


GROUPS: dict[str, Mt4Group] = {g.group: g for g in [
    Mt4Group("MT4_RETAIL", "real\\uk\\std", "UK", "std", 1.0, 20.0, 0.0, 30),
    Mt4Group("MT4_RETAIL", "real\\uk\\raw", "UK", "raw", 0.0, 0.0, 7.0, 30),
    Mt4Group("MT4_RETAIL", "real\\svg\\std", "SVG", "std", 1.2, 25.0, 0.0, 500),
    Mt4Group("MT4_RETAIL", "real\\svg\\raw", "SVG", "raw", 0.0, 0.0, 7.0, 500),
    Mt4Group("MT4_PRIME", "b2b\\prime\\a", "B2B", "b2b", 0.1, 3.0, 4.0, 100),
    Mt4Group("MT4_PRIME", "b2b\\prime\\b", "B2B", "b2b", 0.2, 5.0, 3.0, 100),
    Mt4Group("MT4_RETAIL", "coverage\\retail", "", "coverage", 0.0, 0.0, 0.0, 1),
    Mt4Group("MT4_PRIME", "coverage\\prime", "", "coverage", 0.0, 0.0, 0.0, 1),
]}

# (server, login, name)
COVERAGE_ACCOUNTS = [
    ("MT4_RETAIL", 70000, "COVERAGE RETAIL NET"),
    ("MT4_RETAIL", 70100, "COVERAGE UK MARKUP"),
    ("MT4_RETAIL", 70200, "COVERAGE SVG MARKUP"),
    ("MT4_PRIME", 70001, "COVERAGE B2B NET"),
    ("MT4_PRIME", 70300, "COVERAGE NBC DROP COPY"),
]


@dataclass(frozen=True)
class Segment:
    share: float
    p_trade_day: float    # chance of trading on a given day
    per_day: float        # mean positions on a trading day
    hold_minutes: float   # mean holding time
    lots_median: float
    deposit_median: float


SEGMENTS: dict[str, Segment] = {
    "casual": Segment(0.55, 0.25, 2.0, 240, 0.10, 300),
    "day_trader": Segment(0.20, 0.70, 6.0, 60, 0.50, 2_000),
    "scalper": Segment(0.08, 0.80, 25.0, 3, 1.00, 3_000),
    "toxic": Segment(0.02, 0.80, 20.0, 2, 2.00, 10_000),
    "swing": Segment(0.12, 0.35, 1.5, 5_760, 0.30, 1_500),
    "whale": Segment(0.03, 0.50, 4.0, 600, 5.00, 50_000),
}
B2B_SEGMENT = Segment(0.0, 0.95, 30.0, 90, 5.00, 1_000_000)

COUNTRIES = [  # (ISO, name, weight)
    ("GB", "United Kingdom", 14), ("DE", "Germany", 9), ("FR", "France", 5),
    ("IT", "Italy", 6), ("ES", "Spain", 6), ("PL", "Poland", 4), ("NL", "Netherlands", 3),
    ("AE", "United Arab Emirates", 7), ("SA", "Saudi Arabia", 3), ("ZA", "South Africa", 5),
    ("NG", "Nigeria", 4), ("KE", "Kenya", 2), ("MY", "Malaysia", 6), ("TH", "Thailand", 4),
    ("VN", "Vietnam", 5), ("ID", "Indonesia", 3), ("PH", "Philippines", 2),
    ("BR", "Brazil", 4), ("MX", "Mexico", 3), ("CL", "Chile", 2),
]
CITIES = {
    "GB": ["London", "Manchester", "Leeds"], "DE": ["Berlin", "Munich", "Hamburg"],
    "FR": ["Paris", "Lyon"], "IT": ["Milan", "Rome"], "ES": ["Madrid", "Barcelona"],
    "PL": ["Warsaw", "Krakow"], "NL": ["Amsterdam"], "AE": ["Dubai", "Abu Dhabi"],
    "SA": ["Riyadh", "Jeddah"], "ZA": ["Johannesburg", "Cape Town"], "NG": ["Lagos", "Abuja"],
    "KE": ["Nairobi"], "MY": ["Kuala Lumpur"], "TH": ["Bangkok"], "VN": ["Hanoi", "Ho Chi Minh City"],
    "ID": ["Jakarta"], "PH": ["Manila"], "BR": ["Sao Paulo", "Rio de Janeiro"],
    "MX": ["Mexico City"], "CL": ["Santiago"],
}
FIRST_NAMES = [
    "James", "Oliver", "Amelia", "Sophie", "Lukas", "Anna", "Marco", "Giulia", "Carlos", "Lucia",
    "Piotr", "Kasia", "Omar", "Fatima", "Ahmed", "Layla", "Thabo", "Naledi", "Chinedu", "Ngozi",
    "Wei", "Mei", "Arif", "Siti", "Minh", "Linh", "Budi", "Ayu", "Joao", "Mariana", "Diego",
    "Valentina", "Daniel", "Emma", "Noah", "Mia", "Yusuf", "Zara", "Ravi", "Priya",
]
LAST_NAMES = [
    "Smith", "Jones", "Taylor", "Muller", "Schmidt", "Rossi", "Bianchi", "Garcia", "Lopez",
    "Kowalski", "Nowak", "Haddad", "Rahman", "Al Mansoori", "Nkosi", "Dlamini", "Okafor", "Adeyemi",
    "Tan", "Lim", "Nguyen", "Tran", "Santoso", "Wijaya", "Silva", "Santos", "Hernandez", "Martinez",
    "Brown", "Wilson", "Khan", "Patel", "Ali", "Chen", "Wong", "Kumar",
]
B2B_NAMES = [
    "Alpha Capital Ltd", "Northgate Asset Management", "Bluewater Brokers", "Kestrel Markets",
    "Meridian White Label", "Orion Fund SPC", "Harbour FX Partners", "Summit Prime Services",
]
