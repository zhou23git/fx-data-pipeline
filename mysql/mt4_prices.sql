-- MT4 prices for the local `mt4` schema: the MT4 MySQL export table
-- MT4_PRICES, cut down to the fields Josh chose. One row per symbol holding
-- the latest quote, overwritten on every update, so there is no history.
--
-- Josh's end-of-day snapshot is whatever this table holds at 16:59:59 New
-- York time. Here the hourly process fills it with fake prices on its 16:55
-- New York run (fxgen/prices.py).
--
-- Run after mt4_config.sql: mysql -u root -p mt4 < mt4_prices.sql

USE mt4;

CREATE TABLE MT4_PRICES (
    SERVER       VARCHAR(16) NOT NULL,   -- trade/mt4
    SYMBOL       VARCHAR(16) NOT NULL,   -- MT4_SYMBOLS.SYMBOL
    BID          DOUBLE      NOT NULL,   -- raw quote, before group SPREAD_DIFF
    ASK          DOUBLE      NOT NULL,
    MODIFY_TIME  DATETIME    NOT NULL,   -- last update, GMT
    PRIMARY KEY (SERVER, SYMBOL)
);
