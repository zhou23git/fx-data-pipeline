-- MT4 configuration and accounts, modelled on the MT4 Manager API records
-- (ConSymbolGroup, ConSymbol, ConGroup, ConGroupSec, ConGroupMargin) and the
-- MT4 MySQL export table MT4_USERS.
--
-- Differences from a real MT4 server, on purpose:
--   * SERVER column on every table. Real MT4 servers each have their own
--     database; here MT4_RETAIL and MT4_PRIME share one schema.
--   * Cosmetic/technical fields are left out (SMTP, news, templates, colours,
--     quote filters, trading sessions, internal hashes).
--
-- Run as: mysql -u root -p mt4 < mt4_config.sql

USE mt4;

-- ---------------------------------------------------------------------------
-- Security groups (ConSymbolGroup). MT4 has 32 slots, index 0-31. Every symbol
-- belongs to one, and group-level settings (spread markup, commission, lot
-- limits) are set per security group, not per symbol.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_SECURITIES (
    SERVER       VARCHAR(16) NOT NULL,
    SEC_INDEX    TINYINT     NOT NULL,          -- 0-31
    NAME         VARCHAR(16) NOT NULL,          -- e.g. Forex, Metals
    DESCRIPTION  VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (SERVER, SEC_INDEX)
);

-- ---------------------------------------------------------------------------
-- Symbols (ConSymbol), cut down to the fields this project uses.
-- SYMBOL is wider than real MT4 (11 characters) to fit suffixes like .retail.
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
    SWAP_LONG      DOUBLE      NULL,          -- points; set daily by a plugin
    SWAP_SHORT     DOUBLE      NULL,
    PRIMARY KEY (SERVER, SYMBOL)
);

-- ---------------------------------------------------------------------------
-- Client groups (ConGroup), one row per group. Cut down to the fields this
-- project uses; entities are simulated by login ranges, not by group COMPANY.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_GROUPS (
    SERVER    VARCHAR(16) NOT NULL,
    `GROUP`   VARCHAR(16) NOT NULL,     -- e.g. RetailUSD
    CURRENCY  VARCHAR(12) NOT NULL,     -- deposit currency
    PRIMARY KEY (SERVER, `GROUP`)
);

-- ---------------------------------------------------------------------------
-- Group settings per security group (ConGroupSec): one row per group per
-- security group, cut down to markup, commission and lot limits.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_GROUP_SECURITIES (
    SERVER       VARCHAR(16)  NOT NULL,
    `GROUP`      VARCHAR(16)  NOT NULL,
    SEC_INDEX    TINYINT      NOT NULL,                -- MT4_SECURITIES.SEC_INDEX
    SPREAD_DIFF  INT          NOT NULL DEFAULT 0,      -- group markup in points; price = SPREAD_DIFF * MT4_SYMBOLS.POINT
    COMM_BASE    INT          NOT NULL DEFAULT 0,      -- USD per 100,000 USD notional
    LOT_MIN      DECIMAL(8,2) NOT NULL DEFAULT 0.01,   -- lots
    LOT_MAX      DECIMAL(8,2) NOT NULL DEFAULT 100,
    LOT_STEP     DECIMAL(8,2) NOT NULL DEFAULT 0.01,
    PRIMARY KEY (SERVER, `GROUP`, SEC_INDEX)
);

-- ---------------------------------------------------------------------------
-- Per-symbol overrides inside a group (ConGroupMargin): only for symbols whose
-- swaps or margin differ from the symbol defaults for this group. Optional.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_GROUP_MARGINS (
    SERVER          VARCHAR(16) NOT NULL,
    `GROUP`         VARCHAR(16) NOT NULL,
    SYMBOL          VARCHAR(12) NOT NULL,
    SWAP_LONG       DOUBLE      NOT NULL DEFAULT 0,
    SWAP_SHORT      DOUBLE      NOT NULL DEFAULT 0,
    MARGIN_DIVIDER  DOUBLE      NOT NULL DEFAULT 1,
    PRIMARY KEY (SERVER, `GROUP`, SYMBOL)
);

-- ---------------------------------------------------------------------------
-- Accounts (MT4_USERS export), cut down to the fields this project uses.
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
    REGDATE        DATETIME     NOT NULL,                -- registration, server time
    PRIMARY KEY (SERVER, LOGIN)
);
