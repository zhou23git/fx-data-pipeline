-- MT4 daily summaries for the local `mt4` schema: the MT4 MySQL export table
-- MT4_DAILY, reduced by Josh to the summary of each client statement (no
-- ticket list). One row per login per statement, written at end of day with
-- the statement CSV (fxgen/statements.py). Money is DOUBLE in the deposit
-- currency, as in MT4_TRADES.
--
-- Run after mt4_config.sql: mysql -u root -p mt4 < mt4_daily.sql

USE mt4;

CREATE TABLE MT4_DAILY (
    SERVER            VARCHAR(16) NOT NULL,   -- trade/mt4
    LOGIN             INT         NOT NULL,   -- MT4_USERS.LOGIN
    STATEMENT_DATE    DATE        NOT NULL,   -- trading day, ending 17:00 New York
    PREVIOUS_BALANCE  DOUBLE      NOT NULL,   -- NEW_BALANCE of the login's last statement
    DEPOSITS          DOUBLE      NOT NULL,   -- the day's deposits and withdrawals, net
    PROFIT_CLOSED     DOUBLE      NOT NULL,   -- commission + swaps + profit of tickets closed that day
    NEW_BALANCE       DOUBLE      NOT NULL,   -- PREVIOUS_BALANCE + DEPOSITS + PROFIT_CLOSED
    PROFIT_OPEN       DOUBLE      NOT NULL,   -- commission + swaps + profit of tickets open at the close
    PL                DOUBLE      NOT NULL,   -- NEW_BALANCE + PROFIT_OPEN
    PRIMARY KEY (SERVER, LOGIN, STATEMENT_DATE)
);
