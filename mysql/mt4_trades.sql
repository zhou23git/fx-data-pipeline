-- MT4 trades for the local `mt4` schema: the MT4 MySQL export table
-- MT4_TRADES (TradeRecord in the Manager API), cut down to the fields Josh
-- chose. Field meanings are in docs/domain-notes.md ("MT4 trades").
--
-- One row per ticket. Like real MT4, deposits, withdrawals and credit are rows
-- here too (CMD 6 balance, 7 credit). Prices, rates and money are DOUBLE as in
-- the real export. Times are GMT.
--
-- Run after mt4_config.sql: mysql -u root -p mt4 < mt4_trades.sql

USE mt4;

CREATE TABLE MT4_TRADES (
    SERVER            VARCHAR(16)  NOT NULL,                -- trade/mt4
    TICKET            INT          NOT NULL,                -- XCORE_ORDER_MT4.TICKET
    LOGIN             INT          NOT NULL,                -- MT4_USERS.LOGIN
    SYMBOL            VARCHAR(16)  NOT NULL DEFAULT '',     -- MT4 symbol; empty on balance and credit rows
    DIGITS            TINYINT      NOT NULL DEFAULT 0,      -- price rounding
    CMD               TINYINT      NOT NULL,                -- 0 buy, 1 sell, 2-5 pending, 6 balance, 7 credit
    VOLUME            INT          NOT NULL DEFAULT 0,      -- whole number, 100 = 1 lot
    OPEN_TIME         DATETIME     NOT NULL,                -- from the opening order MT4 row
    OPEN_PRICE        DOUBLE       NOT NULL DEFAULT 0,      -- locked in on open
    CLOSE_TIME        DATETIME     NOT NULL DEFAULT '1970-01-01 00:00:00',  -- from the closing row; 1970-01-01 while open
    CLOSE_PRICE       DOUBLE       NOT NULL DEFAULT 0,      -- floats with the market until closed
    CONV_RATE1        DOUBLE       NOT NULL DEFAULT 0,      -- base currency -> deposit currency at open (Josh's definition)
    CONV_RATE2        DOUBLE       NOT NULL DEFAULT 0,      -- base currency -> deposit currency at close
    COMMISSION        DOUBLE       NOT NULL DEFAULT 0,      -- open side at open; close side added at close
    COMMISSION_AGENT  DOUBLE       NOT NULL DEFAULT 0,      -- earned by the rebate login (MT4_USERS.AGENT_ACCOUNT)
    SWAPS             DOUBLE       NOT NULL DEFAULT 0,      -- running total, one day added each rollover; locked at close
    PROFIT            DOUBLE       NOT NULL DEFAULT 0,      -- floats with CLOSE_PRICE until closed, then locked
    COMMENT           VARCHAR(32)  NOT NULL DEFAULT '',     -- to be explained by Josh
    PRIMARY KEY (SERVER, TICKET),
    INDEX (SERVER, LOGIN),
    CHECK (CMD BETWEEN 0 AND 7)
);
