"""Minute-level mid prices for every instrument.

Drivers follow a random walk with session-dependent volatility and stay flat
while the market is closed. Crosses are computed from the drivers.
"""
from __future__ import annotations

import math
import random
from array import array
from datetime import date, datetime, timedelta
from itertools import accumulate

from fxgen.reference import CROSSES, SYMBOLS
from fxgen.timeutil import is_market_open, server_date

MINUTES_PER_YEAR = 252 * 1440


def _session_weight(utc: datetime) -> float:
    """Relative activity: busiest in the London/New York overlap, quiet in Asia."""
    h = utc.hour
    if 12 <= h < 16:
        return 2.0
    if 7 <= h < 12 or 16 <= h < 20:
        return 1.4
    if 20 <= h < 22:
        return 0.5
    return 0.7


class Market:
    def __init__(self, start: datetime, end: datetime, rng: random.Random):
        self.start = start
        self.n = int((end - start).total_seconds() // 60)
        self.open = bytearray(self.n)
        weights = [0.0] * self.n
        day_idx: dict[date, list[int]] = {}
        for i in range(self.n):
            t = start + timedelta(minutes=i)
            if is_market_open(t):
                self.open[i] = 1
                weights[i] = _session_weight(t)
                day_idx.setdefault(server_date(t), []).append(i)

        # Trading days (server calendar) with their open minutes and cumulative
        # weights for sampling order times.
        self.days: dict[date, tuple[list[int], list[float]]] = {
            d: (idx, list(accumulate(weights[i] for i in idx))) for d, idx in day_idx.items()
        }
        self.trading_days = sorted(self.days)

        # next_open[i]: first open minute at or after i (n if none).
        self.next_open = array("i", [0]) * self.n
        nxt = self.n
        for i in range(self.n - 1, -1, -1):
            if self.open[i]:
                nxt = i
            self.next_open[i] = nxt
        self.last_open = max(i for i in range(self.n) if self.open[i])

        self.mid: dict[str, array] = {}
        for name, s in SYMBOLS.items():
            if name in CROSSES:
                continue
            path = array("d", [0.0]) * self.n
            price = s.start
            base_sigma = s.vol / math.sqrt(MINUTES_PER_YEAR)
            for i in range(self.n):
                if self.open[i]:
                    price *= math.exp(rng.gauss(0.0, base_sigma * weights[i]))
                path[i] = price
            self.mid[name] = path
        for name, (a, op, b) in CROSSES.items():
            pa, pb = self.mid[a], self.mid[b]
            self.mid[name] = array("d", (x / y if op == "/" else x * y for x, y in zip(pa, pb)))

    def index(self, utc: datetime) -> int:
        return min(self.n - 1, max(0, int((utc - self.start).total_seconds() // 60)))

    def time_of(self, i: int) -> datetime:
        return self.start + timedelta(minutes=i)

    def usd_per(self, currency: str, i: int) -> float:
        """Value of one unit of `currency` in USD at minute i."""
        if currency == "USD":
            return 1.0
        direct = currency + "USD"
        if direct in self.mid:
            return self.mid[direct][i]
        return 1.0 / self.mid["USD" + currency][i]

    def eod_index(self, d: date) -> int:
        """Last open minute of a server trading day: the rollover mark."""
        return self.days[d][0][-1]
