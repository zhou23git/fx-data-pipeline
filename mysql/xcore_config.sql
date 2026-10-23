-- XCore (PrimeXM bridge) configuration tables.
--
-- Table order follows Josh's dependency order (docs/domain-notes.md):
--   1. Providers (PrimeXM makers)
--   2. XCore symbols. (The provider symbol -> XCore symbol mapping is not
--      modelled: Josh skipped it.)
--   3. Liquidity pools (providers per XCore symbol)
--   4. Profiles (pool and markup per symbol)
--   5. Connectors (PrimeXM takers): the MT4 server, plus one per giveup
--      coverage login
--   6. Connector accounts (children of a connector, handle trading; each
--      has a pool and a profile)
--   (Connector streams and an XCore -> MT4 symbol mapping table are not
--   modelled: Josh dropped them. XCore -> MT4 symbols follow a rule instead,
--   see domain-notes.md.)
--
-- Also: the config audit log, one row per config change.
--
-- Also: giveup rules (drop copies to MT4 coverage logins).
--
-- Trade tables (ORDER, ORDER_MT4, LEG, DEAL) are left out of this file for
-- now. Config rows are filled in by Josh (mysql/xcore_seed.sql).
--
-- Run as: mysql -u root -p xcore < xcore_config.sql

USE xcore;

-- ---------------------------------------------------------------------------
-- 1. Providers: PrimeXM makers, one row per liquidity provider.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_PROVIDERS (
    PROVIDER_ID     INT          NOT NULL AUTO_INCREMENT,
    NAME            VARCHAR(32)  NOT NULL,          -- e.g. BankA
    SENDER_COMP_ID  VARCHAR(32)  NOT NULL DEFAULT '',  -- FIX: our side of the session
    TARGET_COMP_ID  VARCHAR(32)  NOT NULL DEFAULT '',  -- FIX: the provider
    ENABLE          TINYINT      NOT NULL DEFAULT 1,
    PRIMARY KEY (PROVIDER_ID),
    UNIQUE KEY (NAME)
);

-- ---------------------------------------------------------------------------
-- 2. XCore symbols: the instruments every MT4 symbol aggregates to. Modelled
--    on Josh's reference table from work, not on PrimeXM's own schema (which
--    isn't public).
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_SYMBOLS (
    SYMBOL  VARCHAR(12) NOT NULL,      -- e.g. EUR/USD, WTI
    TYPE    VARCHAR(8)  NOT NULL,      -- FX or CFD; metals count as FX
    CCY1    VARCHAR(12) NOT NULL,      -- base currency; the underlying for CFDs (USOIL)
    CCY2    VARCHAR(12) NOT NULL,      -- quote currency
    PRIMARY KEY (SYMBOL)
);

-- ---------------------------------------------------------------------------
-- 3. Liquidity pools: the set of providers behind each XCore symbol.
--    Changed with fxgen/pools.py, which logs every change.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_LIQUIDITY_POOLS (
    POOL_ID  INT          NOT NULL AUTO_INCREMENT,
    NAME     VARCHAR(32)  NOT NULL,             -- e.g. Bank_FX
    PRIMARY KEY (POOL_ID),
    UNIQUE KEY (NAME)
);

CREATE TABLE XCORE_LIQUIDITY_POOL_PROVIDERS (
    POOL_ID       INT         NOT NULL,
    XCORE_SYMBOL  VARCHAR(12) NOT NULL,
    PROVIDER_ID   VARCHAR(64) NOT NULL,         -- CSV of XCORE_PROVIDERS.PROVIDER_ID, ascending, e.g. 1,3
    PRIMARY KEY (POOL_ID, XCORE_SYMBOL),
    FOREIGN KEY (POOL_ID) REFERENCES XCORE_LIQUIDITY_POOLS (POOL_ID),
    FOREIGN KEY (XCORE_SYMBOL) REFERENCES XCORE_SYMBOLS (SYMBOL)
);

-- ---------------------------------------------------------------------------
-- 4. Profiles, and per profile and symbol: the liquidity pool used and the
--    XCore markup (layer 1 of 3 in domain-notes.md, "Markup: lives in several
--    places"). Changed with fxgen/profiles.py, which logs every change.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_PROFILES (
    PROFILE_ID  INT          NOT NULL AUTO_INCREMENT,
    NAME        VARCHAR(32)  NOT NULL,             -- e.g. Retail
    PRIMARY KEY (PROFILE_ID),
    UNIQUE KEY (NAME)
);

CREATE TABLE XCORE_PROFILE_SYMBOLS (
    PROFILE_ID    INT           NOT NULL,
    XCORE_SYMBOL  VARCHAR(12)   NOT NULL,
    POOL_ID       INT           NOT NULL,
    MARKUP_BID    DECIMAL(10,5) NOT NULL DEFAULT 0,  -- price added to the bid; <= 0, e.g. -0.00002
    MARKUP_ASK    DECIMAL(10,5) NOT NULL DEFAULT 0,  -- price added to the ask; >= 0, e.g. +0.00002
    PRIMARY KEY (PROFILE_ID, XCORE_SYMBOL),
    CHECK (MARKUP_BID <= 0),
    CHECK (MARKUP_ASK >= 0),
    FOREIGN KEY (PROFILE_ID) REFERENCES XCORE_PROFILES (PROFILE_ID),
    FOREIGN KEY (XCORE_SYMBOL) REFERENCES XCORE_SYMBOLS (SYMBOL),
    FOREIGN KEY (POOL_ID) REFERENCES XCORE_LIQUIDITY_POOLS (POOL_ID)
);

-- ---------------------------------------------------------------------------
-- 5. Connectors: PrimeXM takers, the connections XCore trades with. One for
--    the MT4 server, and one per giveup coverage login.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_CONNECTORS (
    CONNECTOR_ID  INT          NOT NULL AUTO_INCREMENT,
    NAME          VARCHAR(32)  NOT NULL,            -- e.g. trade/mt4, trade/uk_cov_100
    DESCRIPTION   VARCHAR(64)  NOT NULL DEFAULT '',
    PRIMARY KEY (CONNECTOR_ID),
    UNIQUE KEY (NAME)
);

-- ---------------------------------------------------------------------------
-- 6. Connector accounts (children of a connector): handle trading. A
--    connector can have several, e.g. one per business on trade/mt4.
--    `GROUP`, LOGIN and LEAD_SOURCE say which MT4 trades an account takes:
--    each is a comma-separated list, or * for anything; NULL matches nothing.
--    A trade matches when its MT4 login matches all three.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_CONNECTOR_ACCOUNTS (
    ACCOUNT_ID    INT          NOT NULL AUTO_INCREMENT,
    CONNECTOR_ID  INT          NOT NULL,
    NAME          VARCHAR(32)  NOT NULL,            -- e.g. Retail, uk_cov_100
    `GROUP`       VARCHAR(255) NULL,                -- MT4_GROUPS.GROUP list, e.g. RetailUSD,RetailEUR
    LOGIN         VARCHAR(255) NULL,                -- MT4 login list, e.g. 20,50
    LEAD_SOURCE   VARCHAR(255) NULL,                -- MT4_USERS.LEAD_SOURCE list, e.g. WL
    POOL_ID       INT          NOT NULL,
    PROFILE_ID    INT          NOT NULL,
    PRIMARY KEY (ACCOUNT_ID),
    UNIQUE KEY (CONNECTOR_ID, NAME),
    FOREIGN KEY (CONNECTOR_ID) REFERENCES XCORE_CONNECTORS (CONNECTOR_ID),
    FOREIGN KEY (POOL_ID) REFERENCES XCORE_LIQUIDITY_POOLS (POOL_ID),
    FOREIGN KEY (PROFILE_ID) REFERENCES XCORE_PROFILES (PROFILE_ID)
);

-- ---------------------------------------------------------------------------
-- Giveups: each rule sends a drop copy of every matching trade to the MT4
-- coverage login in TARGET. Match fields hold XCore's own patterns, kept
-- verbatim: * = anything, NZ_* = prefix, comma-separated lists such as
-- 'UK_*, NZ_*', ! for negation (e.g. '!XAUUSD, *'). BOOK holds XCore's
-- values as they are (b_only, any, *). GIVEUP_ID is the rule order.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_GIVEUPS (
    GIVEUP_ID    INT          NOT NULL AUTO_INCREMENT,
    CONNECTOR    VARCHAR(255) NOT NULL,            -- e.g. trade/mt4
    ACCOUNT      VARCHAR(255) NOT NULL,            -- connector account name pattern
    SYMBOL       VARCHAR(255) NOT NULL,            -- XCore symbol pattern
    `GROUP`      VARCHAR(255) NOT NULL,            -- MT4 group pattern
    LOGIN        VARCHAR(255) NOT NULL,            -- MT4 login pattern
    LEAD_SOURCE  VARCHAR(255) NOT NULL,            -- MT4 lead source pattern
    BOOK         VARCHAR(32)  NOT NULL,            -- b_only, any, *
    TARGET       INT          NOT NULL,            -- coverage login, MT4_USERS.LOGIN
    PRIMARY KEY (GIVEUP_ID)
);

-- ---------------------------------------------------------------------------
-- Config audit log: one row per change, written in the same transaction as
-- the change. MESSAGE is a fixed-format sentence carrying the old and new
-- value, so settings at any time can be rebuilt by popping back from the
-- latest entry. LOG_TIME never goes backwards, so LOG_ID order = time order.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_CONFIG_AUDIT_LOG (
    LOG_ID    BIGINT       NOT NULL AUTO_INCREMENT,
    LOG_TIME  DATETIME(3)  NOT NULL,           -- GMT, milliseconds
    MESSAGE   VARCHAR(512) NOT NULL,
    PRIMARY KEY (LOG_ID)
);
