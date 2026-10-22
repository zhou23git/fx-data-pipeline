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
-- Accounts: the MT4 MySQL export table, column for column, plus SERVER.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_USERS (
    SERVER              VARCHAR(16)  NOT NULL,
    LOGIN               INT          NOT NULL,
    `GROUP`             VARCHAR(16)  NOT NULL,
    ENABLE              INT          NOT NULL DEFAULT 1,
    ENABLE_CHANGE_PASS  INT          NOT NULL DEFAULT 1,
    ENABLE_READONLY     INT          NOT NULL DEFAULT 0,
    ENABLE_OTP          INT          NOT NULL DEFAULT 0,
    PASSWORD_PHONE      VARCHAR(32)  NOT NULL DEFAULT '',
    NAME                VARCHAR(128) NOT NULL DEFAULT '',
    COUNTRY             VARCHAR(32)  NOT NULL DEFAULT '',
    CITY                VARCHAR(32)  NOT NULL DEFAULT '',
    STATE               VARCHAR(32)  NOT NULL DEFAULT '',
    ZIPCODE             VARCHAR(16)  NOT NULL DEFAULT '',
    ADDRESS             VARCHAR(128) NOT NULL DEFAULT '',
    LEAD_SOURCE         VARCHAR(32)  NOT NULL DEFAULT '',
    PHONE               VARCHAR(32)  NOT NULL DEFAULT '',
    EMAIL               VARCHAR(48)  NOT NULL DEFAULT '',
    COMMENT             VARCHAR(64)  NOT NULL DEFAULT '',
    ID                  VARCHAR(32)  NOT NULL DEFAULT '',     -- free field; often the CRM id
    STATUS              VARCHAR(16)  NOT NULL DEFAULT '',
    REGDATE             DATETIME     NOT NULL,                -- server time
    LASTDATE            DATETIME     NOT NULL,
    LEVERAGE            INT          NOT NULL DEFAULT 100,
    AGENT_ACCOUNT       INT          NOT NULL DEFAULT 0,      -- IB login that earns agent commission
    TIMESTAMP           INT          NOT NULL DEFAULT 0,      -- unix time of last change
    BALANCE             DOUBLE       NOT NULL DEFAULT 0,
    PREVMONTHBALANCE    DOUBLE       NOT NULL DEFAULT 0,
    PREVBALANCE         DOUBLE       NOT NULL DEFAULT 0,
    CREDIT              DOUBLE       NOT NULL DEFAULT 0,
    INTERESTRATE        DOUBLE       NOT NULL DEFAULT 0,
    TAXES               DOUBLE       NOT NULL DEFAULT 0,
    SEND_REPORTS        INT          NOT NULL DEFAULT 1,
    MQID                INT UNSIGNED NOT NULL DEFAULT 0,
    USER_COLOR          INT          NOT NULL DEFAULT 0,
    EQUITY              DOUBLE       NOT NULL DEFAULT 0,
    MARGIN              DOUBLE       NOT NULL DEFAULT 0,
    MARGIN_LEVEL        DOUBLE       NOT NULL DEFAULT 0,
    MARGIN_FREE         DOUBLE       NOT NULL DEFAULT 0,
    CURRENCY            VARCHAR(16)  NOT NULL DEFAULT 'USD',
    API_DATA            BLOB         NULL,
    MODIFY_TIME         DATETIME     NOT NULL,
    PRIMARY KEY (SERVER, LOGIN)
);
