-- MT4 configuration and accounts for the local `mt4` schema.
--
-- Only the tables in use so far, cut down to the fields this project needs.
-- Tables and fields are added as the simulation needs them. Modelled on the
-- MT4 Manager API records (ConSymbolGroup, ConSymbol, ConGroup, ConGroupSec)
-- and the MT4 MySQL export table MT4_USERS.
--
-- Differences from a real MT4 server, on purpose:
--   * SERVER column on every table (one server here: trade/mt4).
--   * SYMBOL is wider than real MT4's 11 characters, to fit .retail.
--   * Times are GMT.
--
-- Run as: mysql -u root -p mt4 < mt4_config.sql

USE mt4;

-- ---------------------------------------------------------------------------
-- Security groups (ConSymbolGroup): 1 FX, 2 METAL, 3 CFD. Group settings
-- (markup, commission, lot limits) are set per security group.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_SECURITIES (
    SERVER       VARCHAR(16) NOT NULL,
    SEC_INDEX    TINYINT     NOT NULL,          -- 0-31
    NAME         VARCHAR(16) NOT NULL,          -- e.g. FX, METAL
    DESCRIPTION  VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (SERVER, SEC_INDEX)
);

-- ---------------------------------------------------------------------------
-- Symbols (ConSymbol).
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_SYMBOLS (
    SERVER         VARCHAR(16) NOT NULL,
    SYMBOL         VARCHAR(16) NOT NULL,      -- e.g. EURUSD.retail
    DESCRIPTION    VARCHAR(64) NOT NULL DEFAULT '',
    CURRENCY       VARCHAR(12) NOT NULL,      -- base currency; USD for oil and indices
    TYPE           TINYINT     NOT NULL,      -- security group, MT4_SECURITIES.SEC_INDEX
    DIGITS         TINYINT     NOT NULL,
    POINT          DOUBLE      NOT NULL,      -- 1 / 10^DIGITS
    CONTRACT_SIZE  DOUBLE      NOT NULL,
    TICK_SIZE      DOUBLE      NOT NULL,      -- equals POINT
    TICK_VALUE     DOUBLE      NOT NULL,      -- TICK_VALUE / TICK_SIZE < 1 marks a mini contract
    SWAP_ENABLE    TINYINT     NOT NULL DEFAULT 1,
    SWAP_LONG      DOUBLE      NULL,          -- price delta (EURUSD -0.00003); set daily by a plugin
    SWAP_SHORT     DOUBLE      NULL,
    PRIMARY KEY (SERVER, SYMBOL)
);

-- ---------------------------------------------------------------------------
-- Client groups (ConGroup). Entities show in login ranges and
-- MT4_USERS.LEAD_SOURCE, not in the group.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_GROUPS (
    SERVER    VARCHAR(16) NOT NULL,
    `GROUP`   VARCHAR(16) NOT NULL,     -- e.g. RetailUSD
    CURRENCY  VARCHAR(12) NOT NULL,     -- deposit currency
    PRIMARY KEY (SERVER, `GROUP`)
);

-- ---------------------------------------------------------------------------
-- Group settings per security group (ConGroupSec): one row per group per
-- security group.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_GROUP_SECURITIES (
    SERVER       VARCHAR(16)  NOT NULL,
    `GROUP`      VARCHAR(16)  NOT NULL,
    SEC_INDEX    TINYINT      NOT NULL,                -- MT4_SECURITIES.SEC_INDEX
    SPREAD_DIFF  INT          NOT NULL DEFAULT 0,      -- group markup in points; price = SPREAD_DIFF * MT4_SYMBOLS.POINT
    COMM_BASE    INT          NOT NULL DEFAULT 0,      -- USD per 100,000 USD notional, per side
    LOT_MIN      DECIMAL(8,2) NOT NULL DEFAULT 0.01,   -- lots
    LOT_MAX      DECIMAL(8,2) NOT NULL DEFAULT 100,
    LOT_STEP     DECIMAL(8,2) NOT NULL DEFAULT 0.01,
    PRIMARY KEY (SERVER, `GROUP`, SEC_INDEX)
);

-- ---------------------------------------------------------------------------
-- Accounts (MT4_USERS export).
-- Login ranges: 10-50 House, 100-400 Coverage, 500-900 B2B, 1000-8999 Retail,
-- 9990-9999 Rebate, 100000 White Label coverage, 100001-100100 White Label.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_USERS (
    SERVER         VARCHAR(16)  NOT NULL,
    LOGIN          INT          NOT NULL,
    `GROUP`        VARCHAR(16)  NOT NULL,
    NAME           VARCHAR(128) NOT NULL DEFAULT '',
    LEAD_SOURCE    VARCHAR(32)  NOT NULL DEFAULT '',     -- entity and desk, e.g. NZ_TRD, UK_COV, WL
    PHONE          VARCHAR(32)  NOT NULL DEFAULT '',
    COMMENT        VARCHAR(64)  NOT NULL DEFAULT '',
    AGENT_ACCOUNT  INT          NOT NULL DEFAULT 0,      -- rebate login paid for this account; 0 = none
    CURRENCY       VARCHAR(16)  NOT NULL,                -- deposit currency, same as the group's
    REGDATE        DATETIME     NOT NULL,                -- registration, GMT
    PRIMARY KEY (SERVER, LOGIN)
);
