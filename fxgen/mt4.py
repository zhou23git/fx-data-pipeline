"""An MT4 server's trade table: one row per ticket, updated in place."""
from __future__ import annotations

from datetime import datetime, timedelta

from fxgen.market import Market
from fxgen.reference import GROUPS, SERVERS, SYMBOLS
from fxgen.timeutil import MT4_EPOCH, fmt_mt4, server_date, unix

CMD_BUY, CMD_SELL, CMD_BALANCE = 0, 1, 6


def swap_nights(open_utc: datetime, close_utc: datetime) -> int:
    """Rollovers held: each server weekday crossed counts once, Wednesday three
    times to cover the weekend."""
    d, end = server_date(open_utc), server_date(close_utc)
    nights = 0
    while d < end:
        if d.weekday() < 5:
            nights += 3 if d.weekday() == 2 else 1
        d += timedelta(days=1)
    return nights


class Mt4Book:
    def __init__(self, server: str, market: Market):
        self.server = SERVERS[server]
        self.market = market
        self.next_ticket = self.server.ticket_start
        self.trades: dict[int, dict] = {}

    def _ticket(self) -> int:
        self.next_ticket += 1
        return self.next_ticket

    def balance(self, login: int, amount: float, utc: datetime, comment: str, reason: int = 2) -> int:
        ticket = self._ticket()
        ts = fmt_mt4(utc)
        self.trades[ticket] = dict(
            TICKET=ticket, LOGIN=login, SYMBOL="", DIGITS=0, CMD=CMD_BALANCE, VOLUME=0,
            OPEN_TIME=ts, OPEN_PRICE=0, SL=0, TP=0, CLOSE_TIME=ts, EXPIRATION=MT4_EPOCH, REASON=reason,
            CONV_RATE1=0, CONV_RATE2=0, COMMISSION=0, COMMISSION_AGENT=0, SWAPS=0, CLOSE_PRICE=0,
            PROFIT=round(amount, 2), TAXES=0, COMMENT=comment, INTERNAL_ID=0, MARGIN_RATE=0,
            TIMESTAMP=unix(utc), MAGIC=0, GW_VOLUME=0, GW_OPEN_PRICE=0, GW_CLOSE_PRICE=0, MODIFY_TIME=ts,
            _open=utc, _close=utc, _xsym="", _lots=0.0)
        return ticket

    def open(self, login: int, group: str, xsym: str, side: str, lots: float, price: float,
             utc: datetime, comment: str = "", reason: int = 0, magic: int = 0) -> int:
        s = SYMBOLS[xsym]
        i = self.market.index(utc)
        ticket = self._ticket()
        ts = fmt_mt4(utc)
        commission = -GROUPS[group].commission * lots
        self.trades[ticket] = dict(
            TICKET=ticket, LOGIN=login, SYMBOL=xsym + self.server.suffix, DIGITS=s.digits,
            CMD=CMD_BUY if side == "BUY" else CMD_SELL, VOLUME=round(lots * 100),
            OPEN_TIME=ts, OPEN_PRICE=round(price, s.digits), SL=0, TP=0, CLOSE_TIME=MT4_EPOCH,
            EXPIRATION=MT4_EPOCH, REASON=reason, CONV_RATE1=round(self.market.usd_per(s.quote, i), 8),
            CONV_RATE2=0, COMMISSION=round(commission, 2), COMMISSION_AGENT=0, SWAPS=0, CLOSE_PRICE=0,
            PROFIT=0, TAXES=0, COMMENT=comment, INTERNAL_ID=0,
            MARGIN_RATE=round(self.market.usd_per(s.base, i), 8), TIMESTAMP=unix(utc), MAGIC=magic,
            GW_VOLUME=0, GW_OPEN_PRICE=0, GW_CLOSE_PRICE=0, MODIFY_TIME=ts,
            _open=utc, _close=None, _xsym=xsym, _lots=lots, _group=group)
        return ticket

    def close(self, ticket: int, lots: float, price: float, utc: datetime) -> int | None:
        """Close `lots` of a ticket. A partial close leaves the closed part on
        the original ticket and opens the remainder as a new ticket, the way
        MT4 does ("to #new" / "from #old"). Returns the remainder's ticket."""
        t = self.trades[ticket]
        s = SYMBOLS[t["_xsym"]]
        lots = min(lots, t["_lots"])
        remainder = round(t["_lots"] - lots, 2)
        new_ticket = None
        if remainder > 0:
            new_ticket = self._ticket()
            rest = dict(t)
            share = remainder / t["_lots"]
            rest.update(TICKET=new_ticket, VOLUME=round(remainder * 100), _lots=remainder,
                        COMMISSION=round(t["COMMISSION"] * share, 2), COMMENT=f"from #{ticket}")
            self.trades[new_ticket] = rest
            t["COMMISSION"] = round(t["COMMISSION"] - rest["COMMISSION"], 2)
            t["COMMENT"] = f"to #{new_ticket}"
            t.update(VOLUME=round(lots * 100), _lots=lots)
        i = self.market.index(utc)
        direction = 1 if t["CMD"] == CMD_BUY else -1
        close_price = round(price, s.digits)
        conv = self.market.usd_per(s.quote, i)
        nights = swap_nights(t["_open"], utc)
        swap = (s.swap_long if direction == 1 else s.swap_short) * lots * nights
        profit = direction * (close_price - t["OPEN_PRICE"]) * s.contract * lots * conv
        ts = fmt_mt4(utc)
        t.update(CLOSE_TIME=ts, CLOSE_PRICE=close_price, CONV_RATE2=round(conv, 8), SWAPS=round(swap, 2),
                 PROFIT=round(profit, 2), TIMESTAMP=unix(utc), MODIFY_TIME=ts, _close=utc)
        return new_ticket

    def mark_open_trades(self, utc: datetime) -> None:
        """Fill CLOSE_PRICE/PROFIT/SWAPS on still-open trades the way the live
        table shows them: floating at the current price."""
        i = self.market.index(utc)
        for t in self.trades.values():
            if t["_close"] is not None or t["CMD"] == CMD_BALANCE:
                continue
            s = SYMBOLS[t["_xsym"]]
            direction = 1 if t["CMD"] == CMD_BUY else -1
            half = s.spread_pips / 2 * s.pip
            price = self.market.mid[t["_xsym"]][i] - direction * half
            conv = self.market.usd_per(s.quote, i)
            nights = swap_nights(t["_open"], utc)
            swap = (s.swap_long if direction == 1 else s.swap_short) * t["_lots"] * nights
            t.update(CLOSE_PRICE=round(price, s.digits), CONV_RATE2=round(conv, 8), SWAPS=round(swap, 2),
                     PROFIT=round(direction * (price - t["OPEN_PRICE"]) * s.contract * t["_lots"] * conv, 2))
