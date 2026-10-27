-- XCore trade tables, filled by the execution simulation.
-- Field meanings are in docs/domain-notes.md ("Execution tables").
-- Times are epoch milliseconds (GMT); CLOSE_MILLI is always set, a rejection
-- included. A rejected order or leg has fill size and price 0. Sizes are contracts, after converting
-- lots and applying the scaling multiplier (TICK_VALUE / TICK_SIZE).
--
-- Run after xcore_config.sql: mysql -u root -p xcore < xcore_trades.sql

USE xcore;

-- ---------------------------------------------------------------------------
-- Order: the trade request XCore receives. XCore knows its own markup but
-- nothing about MT4 group markups.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_ORDER (
    ORDER_ID     BIGINT        NOT NULL AUTO_INCREMENT,   -- from 1
    SYMBOL       VARCHAR(12)   NOT NULL,                  -- XCore symbol
    SIDE         VARCHAR(4)    NOT NULL,                  -- buy / sell
    SUBID1       INT           NULL,                      -- MT4 login, or NULL
    SUBID2       INT           NULL,                      -- MT4 ticket, or NULL
    SUBID3       BIGINT        NULL,                      -- order MT4 CLORDID, or NULL
    AMOUNT       DECIMAL(20,6) NOT NULL,                  -- requested size, same as order MT4 AMOUNT
    PRICE        DECIMAL(18,6) NOT NULL,                  -- raw price + XCore markup bid/ask
    FILLSIZE     DECIMAL(20,6) NOT NULL DEFAULT 0,                -- executed size, passed back to order MT4
    FILLPRICE    DECIMAL(24,12) NOT NULL DEFAULT 0,               -- executed price + XCore markup bid/ask; size-weighted average of legs, unrounded
    OPEN_MILLI   BIGINT        NOT NULL,                  -- request time, a few ms after order MT4 OPEN_MILLI
    CLOSE_MILLI  BIGINT        NOT NULL,                      -- complete time, after open and after every leg's close
    PRIMARY KEY (ORDER_ID),
    INDEX (SUBID1, SUBID2),
    CHECK (SIDE IN ('buy', 'sell')),
    FOREIGN KEY (SYMBOL) REFERENCES XCORE_SYMBOLS (SYMBOL)
);

-- ---------------------------------------------------------------------------
-- Order MT4: one-to-one MT4 extension of an order. One row per MT4 request
-- to open (CLOSE = 0) or close (CLOSE = 1) a ticket, rejected ones included,
-- keyed by CLORDID, the working ticket number. CLORDID reaches XCore as
-- XCORE_ORDER.SUBID3. ORDER_ID was added to the real table later; before it,
-- the join to XCORE_ORDER matched login, symbol, connector and open times
-- within a minute. Here the join is ORDER_ID only. ORDER_ID is NULL from the
-- moment MT4 sends the request until XCore creates the order.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_ORDER_MT4 (
    LOGIN        INT           NOT NULL,                  -- MT4 login
    CLORDID      BIGINT        NOT NULL AUTO_INCREMENT,   -- working ticket number, from 1
    TICKET       INT           NOT NULL,                  -- MT4 ticket number; 0 for a rejected open
    `CLOSE`      TINYINT       NOT NULL,                  -- 0 = opening, 1 = closing
    SYMBOL       VARCHAR(16)   NOT NULL,                  -- MT4 symbol
    SIDE         VARCHAR(4)    NOT NULL,                  -- buy / sell
    AMOUNT       DECIMAL(20,6) NOT NULL,                  -- requested contracts
    PRICE        DECIMAL(18,6) NOT NULL,                  -- raw price + XCore markup + MT4 group markup
    FILLSIZE     DECIMAL(20,6) NOT NULL DEFAULT 0,                -- executed contracts
    FILLPRICE    DECIMAL(18,6) NOT NULL DEFAULT 0,                -- all-in executed price with all markups
    ORDER_ID     BIGINT        NULL,                      -- XCORE_ORDER.ORDER_ID
    OPEN_MILLI   BIGINT        NOT NULL,                  -- ticket request time: the earliest timestamp
    CLOSE_MILLI  BIGINT        NOT NULL,                      -- ticket fill time: the last timestamp
    PRIMARY KEY (CLORDID),
    INDEX (ORDER_ID),
    INDEX (TICKET),
    CHECK (`CLOSE` IN (0, 1)),
    CHECK (SIDE IN ('buy', 'sell')),
    FOREIGN KEY (ORDER_ID) REFERENCES XCORE_ORDER (ORDER_ID)
);

-- ---------------------------------------------------------------------------
-- Leg: a piece of an order sent to a provider. LEG_ID starts at 0 for each
-- order and is assigned by the simulation (MySQL can't auto-increment per
-- order).
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_LEG (
    ORDER_ID     BIGINT        NOT NULL,                  -- parent XCORE_ORDER.ORDER_ID
    LEG_ID       INT           NOT NULL,                  -- 0, 1, 2 ... within the order
    B_BOOK       TINYINT       NOT NULL,                  -- from config: XCORE_PROFILE_SYMBOLS.B_BOOK
    SYMBOL       VARCHAR(12)   NOT NULL,                  -- XCore symbol
    SIDE         VARCHAR(4)    NOT NULL,                  -- buy / sell
    AMOUNT       DECIMAL(20,6) NOT NULL,                  -- requested leg size, smaller than the order size
    PRICE        DECIMAL(18,6) NOT NULL,                  -- requested price: the LP's quoted price
    FILLSIZE     DECIMAL(20,6) NOT NULL DEFAULT 0,                -- LP fill size
    FILLPRICE1   DECIMAL(18,6) NOT NULL DEFAULT 0,                -- LP executed price, raw
    FILLPRICE2   DECIMAL(18,6) NOT NULL DEFAULT 0,                -- LP executed price + XCore markup
    LP           INT           NOT NULL,                  -- provider whose price it executed on; a real LP even when B-booked
    MARKUP_BID   DECIMAL(10,5) NOT NULL DEFAULT 0,        -- XCore markup applied, from the profile symbol at the time; <= 0
    MARKUP_ASK   DECIMAL(10,5) NOT NULL DEFAULT 0,        -- >= 0
    OPEN_MILLI   BIGINT        NOT NULL,                  -- leg request time, a few ms after order OPEN_MILLI
    CLOSE_MILLI  BIGINT        NOT NULL,                      -- leg complete time: the earliest closing timestamp
    PRIMARY KEY (ORDER_ID, LEG_ID),
    CHECK (B_BOOK IN (0, 1)),
    CHECK (MARKUP_BID <= 0),
    CHECK (MARKUP_ASK >= 0),
    CHECK (SIDE IN ('buy', 'sell')),
    FOREIGN KEY (ORDER_ID) REFERENCES XCORE_ORDER (ORDER_ID),
    FOREIGN KEY (SYMBOL) REFERENCES XCORE_SYMBOLS (SYMBOL),
    FOREIGN KEY (LP) REFERENCES XCORE_PROVIDERS (PROVIDER_ID)
);
