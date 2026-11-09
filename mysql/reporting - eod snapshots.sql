-- Open-position snapshots around end of day (Josh, 2026-11-08). Equiti
-- allowed no trading from 16:58 to 17:02 New York. In that window Josh
-- copied every open ticket twice: at 16:59:55, before the day's swap is
-- charged, and at 17:00:05, right after. Nobody can trade in between, so the
-- two copies hold the same tickets and volumes; only SWAPS changes.
--
-- Written by the end-of-day run (fxgen/snapshots.py). Open buy and sell
-- tickets only (CMD 0 and 1), as they are in mt4.MT4_TRADES at that moment:
-- CLOSE_TIME is 1970-01-01, CLOSE_PRICE and PROFIT are marked to the day's
-- price snapshot. Times are GMT, like MT4.
--
-- Run: mysql -u root -p < "reporting - eod snapshots.sql"

CREATE TABLE IF NOT EXISTS reporting.eod_snapshots (
    SnapDate          DATE         NOT NULL,   -- trading day the end of day closes (reference.eod_time.TRADE_DATE)
    SnapTime          DATETIME     NOT NULL,   -- GMT: 16:59:55 or 17:00:05 New York
    SERVER            VARCHAR(16)  NOT NULL,   -- trade/mt4
    TICKET            INT          NOT NULL,
    LOGIN             INT          NOT NULL,
    SYMBOL            VARCHAR(16)  NOT NULL,
    CMD               TINYINT      NOT NULL,   -- 0 buy, 1 sell
    VOLUME            INT          NOT NULL,   -- 100 = 1 lot
    OPEN_TIME         DATETIME     NOT NULL,
    OPEN_PRICE        DOUBLE       NOT NULL,
    CLOSE_TIME        DATETIME     NOT NULL,   -- 1970-01-01 00:00:00: still open
    CLOSE_PRICE       DOUBLE       NOT NULL,   -- end-of-day mark
    CONV_RATE1        DOUBLE       NOT NULL,
    CONV_RATE2        DOUBLE       NOT NULL,
    COMMISSION        DOUBLE       NOT NULL,
    COMMISSION_AGENT  DOUBLE       NOT NULL,
    SWAPS             DOUBLE       NOT NULL,   -- before the day's swap at 16:59:55, after it at 17:00:05
    PROFIT            DOUBLE       NOT NULL,   -- floating, at the end-of-day mark
    COMMENT           VARCHAR(32)  NOT NULL,
    PRIMARY KEY (SnapTime, SERVER, TICKET),
    INDEX (SnapDate, LOGIN)
);
