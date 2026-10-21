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
-- Symbols (ConSymbol)
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_SYMBOLS (
    SERVER              VARCHAR(16) NOT NULL,
    SYMBOL              VARCHAR(12) NOT NULL,      -- e.g. EURUSD.retail
    DESCRIPTION         VARCHAR(64) NOT NULL DEFAULT '',
    SOURCE              VARCHAR(12) NOT NULL DEFAULT '',  -- synonym: feed symbol it copies quotes from
    CURRENCY            VARCHAR(12) NOT NULL,      -- base currency
    TYPE                TINYINT     NOT NULL,      -- security group, MT4_SECURITIES.SEC_INDEX
    DIGITS              TINYINT     NOT NULL,
    POINT               DOUBLE      NOT NULL,      -- 1 / 10^DIGITS
    TRADE               TINYINT     NOT NULL DEFAULT 2,   -- 0 no trading, 1 close only, 2 full
    EXEMODE             TINYINT     NOT NULL DEFAULT 2,   -- 0 request, 1 instant, 2 market
    PROFIT_MODE         TINYINT     NOT NULL DEFAULT 0,   -- 0 forex, 1 CFD, 2 futures
    MARGIN_MODE         TINYINT     NOT NULL DEFAULT 0,   -- 0 forex, 1 CFD, 2 futures, 3 CFD index, 4 CFD leverage
    MARGIN_CURRENCY     VARCHAR(12) NOT NULL,
    CONTRACT_SIZE       DOUBLE      NOT NULL,      -- 100000 for FX, 100 for gold
    TICK_SIZE           DOUBLE      NOT NULL DEFAULT 0,
    TICK_VALUE          DOUBLE      NOT NULL DEFAULT 0,
    SPREAD              INT         NOT NULL DEFAULT 0,   -- fixed spread in points; 0 = floating (feed spread)
    SPREAD_BALANCE      INT         NOT NULL DEFAULT 0,   -- shifts spread toward bid (-) or ask (+)
    STOPS_LEVEL         INT         NOT NULL DEFAULT 0,   -- points
    FREEZE_LEVEL        INT         NOT NULL DEFAULT 0,   -- points
    GTC_PENDINGS        TINYINT     NOT NULL DEFAULT 1,   -- 0 daily, 1 GTC, 2 daily without stops
    SWAP_ENABLE         TINYINT     NOT NULL DEFAULT 1,
    SWAP_TYPE           TINYINT     NOT NULL DEFAULT 0,   -- 0 points, 1 money, 2 interest, 3 margin currency
    SWAP_LONG           DOUBLE      NOT NULL DEFAULT 0,
    SWAP_SHORT          DOUBLE      NOT NULL DEFAULT 0,
    SWAP_ROLLOVER3DAYS  TINYINT     NOT NULL DEFAULT 2,   -- triple swap day: 0 Mon ... 4 Fri
    MARGIN_INITIAL      DOUBLE      NOT NULL DEFAULT 0,   -- 0 = contract size
    MARGIN_MAINTENANCE  DOUBLE      NOT NULL DEFAULT 0,
    MARGIN_HEDGED       DOUBLE      NOT NULL DEFAULT 0,
    MARGIN_DIVIDER      DOUBLE      NOT NULL DEFAULT 1,
    LONG_ONLY           TINYINT     NOT NULL DEFAULT 0,
    INSTANT_MAX_VOLUME  INT         NOT NULL DEFAULT 0,
    QUOTES_DELAY        INT         NOT NULL DEFAULT 0,
    STARTING            INT         NOT NULL DEFAULT 0,   -- trading start, unix time (0 = none)
    EXPIRATION          INT         NOT NULL DEFAULT 0,   -- trading end, unix time (0 = none)
    PRIMARY KEY (SERVER, SYMBOL)
);

-- ---------------------------------------------------------------------------
-- Client groups (ConGroup), one row per group
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_GROUPS (
    SERVER                  VARCHAR(16)  NOT NULL,
    `GROUP`                 VARCHAR(16)  NOT NULL,     -- e.g. real\uk\std (backslashes are literal)
    ENABLE                  TINYINT      NOT NULL DEFAULT 1,
    COMPANY                 VARCHAR(128) NOT NULL DEFAULT '',
    CURRENCY                VARCHAR(12)  NOT NULL DEFAULT 'USD',   -- deposit currency
    DEFAULT_DEPOSIT         DOUBLE       NOT NULL DEFAULT 0,
    DEFAULT_LEVERAGE        INT          NOT NULL DEFAULT 100,
    CREDIT                  DOUBLE       NOT NULL DEFAULT 0,       -- virtual credit
    MARGIN_CALL             INT          NOT NULL DEFAULT 100,     -- margin level %
    MARGIN_STOPOUT          INT          NOT NULL DEFAULT 50,
    MARGIN_TYPE             TINYINT      NOT NULL DEFAULT 0,       -- 0 percent, 1 currency
    MARGIN_MODE             TINYINT      NOT NULL DEFAULT 1,       -- 0 don't use, 1 use all, 2 use profit, 3 use loss
    INTERESTRATE            DOUBLE       NOT NULL DEFAULT 0,
    USE_SWAP                TINYINT      NOT NULL DEFAULT 1,
    REPORTS                 TINYINT      NOT NULL DEFAULT 1,       -- daily statements
    TIMEOUT                 INT          NOT NULL DEFAULT 60,      -- trade confirmation timeout, seconds
    OTP_MODE                TINYINT      NOT NULL DEFAULT 0,
    RIGHTS                  INT          NOT NULL DEFAULT 0,       -- bit mask
    CHECK_IE_PRICES         TINYINT      NOT NULL DEFAULT 0,
    MAXPOSITIONS            INT          NOT NULL DEFAULT 0,       -- 0 = unlimited
    MAXSECURITIES           INT          NOT NULL DEFAULT 0,
    CLOSE_REOPEN            TINYINT      NOT NULL DEFAULT 0,       -- partial close: 1 = close all, reopen remainder
    HEDGE_PROHIBITED        TINYINT      NOT NULL DEFAULT 0,
    CLOSE_FIFO              TINYINT      NOT NULL DEFAULT 0,
    HEDGE_LARGELEG          TINYINT      NOT NULL DEFAULT 0,
    STOPOUT_SKIP_HEDGED     TINYINT      NOT NULL DEFAULT 0,
    ARCHIVE_PERIOD          INT          NOT NULL DEFAULT 90,      -- days inactive before archiving
    ARCHIVE_MAX_BALANCE     INT          NOT NULL DEFAULT 0,
    ARCHIVE_PENDING_PERIOD  INT          NOT NULL DEFAULT 0,
    PRIMARY KEY (SERVER, `GROUP`)
);

-- ---------------------------------------------------------------------------
-- Group settings per security group (ConGroupSec): one row per group per
-- security group. This is where the MT4 group markup (SPREAD_DIFF) and
-- commissions live.
-- Lot fields are in hundredths of a lot: 1 = 0.01 lot, 100 = 1 lot.
-- ---------------------------------------------------------------------------
CREATE TABLE MT4_GROUP_SECURITIES (
    SERVER             VARCHAR(16) NOT NULL,
    `GROUP`            VARCHAR(16) NOT NULL,
    SEC_INDEX          TINYINT     NOT NULL,          -- MT4_SECURITIES.SEC_INDEX
    `SHOW`             TINYINT     NOT NULL DEFAULT 1,  -- group can see these symbols
    TRADE              TINYINT     NOT NULL DEFAULT 1,  -- group can trade them
    EXECUTION          TINYINT     NOT NULL DEFAULT 1,  -- 0 manual, 1 auto, 2 activity
    SPREAD_DIFF        INT         NOT NULL DEFAULT 0,  -- points added to the spread (the group markup)
    COMM_BASE          DOUBLE      NOT NULL DEFAULT 0,  -- commission amount
    COMM_TYPE          TINYINT     NOT NULL DEFAULT 0,  -- 0 money, 1 pips, 2 percent
    COMM_LOTS          TINYINT     NOT NULL DEFAULT 0,  -- 0 per lot, 1 per deal
    COMM_AGENT         DOUBLE      NOT NULL DEFAULT 0,  -- agent (IB) commission
    COMM_AGENT_TYPE    TINYINT     NOT NULL DEFAULT 0,  -- 0 money, 1 pips
    COMM_AGENT_LOTS    TINYINT     NOT NULL DEFAULT 0,  -- 0 per lot, 1 per deal
    COMM_TAX           DOUBLE      NOT NULL DEFAULT 0,
    LOT_MIN            INT         NOT NULL DEFAULT 1,
    LOT_MAX            INT         NOT NULL DEFAULT 10000,
    LOT_STEP           INT         NOT NULL DEFAULT 1,
    IE_DEVIATION       INT         NOT NULL DEFAULT 0,
    CONFIRMATION       TINYINT     NOT NULL DEFAULT 0,
    TRADE_RIGHTS       INT         NOT NULL DEFAULT 0,  -- bit mask
    IE_QUICK_MODE      TINYINT     NOT NULL DEFAULT 0,
    AUTOCLOSEOUT_MODE  TINYINT     NOT NULL DEFAULT 0,
    FREEMARGIN_MODE    TINYINT     NOT NULL DEFAULT 0,
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
