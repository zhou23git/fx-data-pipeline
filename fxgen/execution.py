"""How XCore fills one order: route to a book, price from the pool, sweep or
single-FOK across providers (with last-look rejects), then add markup."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from fxgen.market import Market
from fxgen.reference import PROVIDERS, SYMBOLS
from fxgen.xcore_config import Config


@dataclass
class Quote:
    provider: str
    bid: float
    ask: float


@dataclass
class Leg:
    provider: str
    provider_symbol: str
    qty: float            # XCore units
    qty_multiplier: float
    price: float
    b_book: int
    status: str           # FILLED / REJECTED


@dataclass
class Fill:
    book: str
    rule_id: str
    pool_id: str
    account_profile: str
    stream_profile: str
    markup_pips: float
    band_no: int
    exec_mode: str
    req_price: float      # what the client was quoted on the stream
    lp_price: float       # VWAP of filled legs (0 if nothing filled)
    fill_price: float     # lp_price plus XCore markup, returned to MT4
    filled_qty: float
    status: str           # FILLED / PARTIAL / REJECTED
    legs: list[Leg] = field(default_factory=list)


def _level_size(symbol: str) -> float:
    return 500.0 if SYMBOLS[symbol].asset == "METAL" else 1_000_000.0


def pool_quotes(cfg: Config, pool_id: str, symbol: str, market: Market, i: int,
                rng: random.Random) -> list[Quote]:
    s = SYMBOLS[symbol]
    mid = market.mid[symbol][i]
    quotes = []
    for pid in cfg.pool.get((pool_id, symbol), []):
        p = PROVIDERS[pid]
        half = s.spread_pips * p.spread_mult / 2 * s.pip
        skew = rng.gauss(0.0, 0.2 * s.spread_pips) * s.pip
        quotes.append(Quote(pid, mid - half + skew, mid + half + skew))
    return quotes


def execute(cfg: Config, market: Market, rng: random.Random, *, connector: str, group: str,
            login: int, symbol: str, side: str, qty: float, i: int,
            force_partial: bool = False) -> Fill:
    s = SYMBOLS[symbol]
    sign = 1 if side == "BUY" else -1
    account = cfg.account[connector]
    stream = cfg.stream[connector]
    rule = cfg.route(connector, account["ACCOUNT_ID"], group, login, symbol, qty)
    book = rule["BOOK"]

    quotes = pool_quotes(cfg, account["POOL_ID"], symbol, market, i, rng)
    if not quotes:  # whole pool disabled: XCore rejects
        return Fill(book, rule["RULE_ID"], account["POOL_ID"], account["LIQUIDITY_PROFILE_ID"],
                    stream["LIQUIDITY_PROFILE_ID"], 0.0, 0, "NONE", 0.0, 0.0, 0.0, 0.0, "REJECTED")
    best_bid = max(q.bid for q in quotes)
    best_ask = min(q.ask for q in quotes)
    top = best_ask if side == "BUY" else best_bid

    stream_band, _ = cfg.markup(stream["LIQUIDITY_PROFILE_ID"], symbol, qty)
    stream_pips = stream_band["MARKUP_ASK_PIPS" if side == "BUY" else "MARKUP_BID_PIPS"]
    req_price = top + sign * stream_pips * s.pip

    legs: list[Leg] = []

    def leg(pid: str, qty_: float, price: float, status: str, b_book: int = 0):
        m = cfg.provider_symbol[(pid, symbol)]
        legs.append(Leg(pid, m["PROVIDER_SYMBOL"], qty_, m["QTY_MULTIPLIER"], price, b_book, status))

    setting = cfg.setting[(account["ACCOUNT_ID"], symbol)]
    if book == "B":
        exec_mode = "INTERNAL"
        leg("INTERNAL", qty, top, "FILLED", b_book=1)
    else:
        single = setting["EXECUTION_MODE"] == "SINGLE_FOK" or qty >= setting["FOK_THRESHOLD_QTY"]
        exec_mode = "SINGLE_FOK" if single else "SWEEP"
        remaining = qty
        rejected: set[str] = set()
        if single:
            # One provider takes the full size; full-amount providers widen with size.
            def size_price(q: Quote) -> float:
                px = q.ask if side == "BUY" else q.bid
                if PROVIDERS[q.provider].execution_type == "FULL_AMOUNT":
                    px += sign * (qty / 1_000_000) * 0.05 * s.spread_pips * s.pip
                else:
                    px += sign * (qty / _level_size(symbol)) * 0.3 * s.spread_pips * s.pip
                return px
            for q in sorted(quotes, key=lambda q: sign * size_price(q)):
                if rng.random() < PROVIDERS[q.provider].reject_prob:
                    leg(q.provider, qty, size_price(q), "REJECTED")
                    rejected.add(q.provider)
                    continue
                leg(q.provider, qty, size_price(q), "FILLED")
                remaining = 0
                break
        for _ in range(3):  # sweep rounds, re-sweeping after last-look rejects
            if remaining <= 0:
                break
            levels = []
            for q in quotes:
                if q.provider in rejected:
                    continue
                px = q.ask if side == "BUY" else q.bid
                depth = 1 if PROVIDERS[q.provider].execution_type == "FULL_AMOUNT" else 3
                for k in range(depth):
                    size = remaining if depth == 1 else _level_size(symbol)
                    levels.append((sign * (px + sign * k * 0.3 * s.spread_pips * s.pip), q.provider,
                                   px + sign * k * 0.3 * s.spread_pips * s.pip, size))
            if not levels:
                break
            levels.sort(key=lambda x: (x[0], x[1]))
            take: dict[str, list[float]] = {}
            left = remaining
            for _, pid, px, size in levels:
                if left <= 0:
                    break
                q_ = min(size, left)
                agg = take.setdefault(pid, [0.0, 0.0])
                agg[0] += q_
                agg[1] += q_ * px
                left -= q_
            for n, (pid, (q_, notional)) in enumerate(take.items()):
                vwap = notional / q_
                last = n == len(take) - 1
                if (force_partial and last and len(take) > 1) or rng.random() < PROVIDERS[pid].reject_prob:
                    leg(pid, q_, vwap, "REJECTED")
                    rejected.add(pid)
                else:
                    leg(pid, q_, vwap, "FILLED")
                    remaining -= q_
            if force_partial:
                break

    # Slippage on filled LP legs (B-book fills at the quote).
    for lg in legs:
        if lg.status == "FILLED" and not lg.b_book:
            lg.price += rng.gauss(0.0, 0.05 * s.spread_pips) * s.pip
    filled = [lg for lg in legs if lg.status == "FILLED"]
    filled_qty = sum(lg.qty for lg in filled)
    lp_price = sum(lg.qty * lg.price for lg in filled) / filled_qty if filled_qty else 0.0

    band, band_no = cfg.markup(account["LIQUIDITY_PROFILE_ID"], symbol, filled_qty or qty)
    markup_pips = band["MARKUP_ASK_PIPS" if side == "BUY" else "MARKUP_BID_PIPS"]
    fill_price = lp_price + sign * markup_pips * s.pip if filled_qty else 0.0
    status = "REJECTED" if not filled_qty else ("FILLED" if filled_qty >= qty - 1e-6 else "PARTIAL")
    return Fill(book, rule["RULE_ID"], account["POOL_ID"], account["LIQUIDITY_PROFILE_ID"],
                stream["LIQUIDITY_PROFILE_ID"], markup_pips, band_no, exec_mode, req_price,
                lp_price, fill_price, filled_qty, status, legs)
