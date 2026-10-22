-- XCore (PrimeXM bridge) configuration tables.
--
-- Table order follows Josh's dependency order (docs/domain-notes.md):
--   1. Providers (PrimeXM makers)
--   2. Provider symbol -> XCore symbol mapping
--   3. Liquidity pools (providers per XCore symbol)
--   4. Profiles (markup, commission)
--   5. Connectors (PrimeXM takers, one per MT4 server)
--   6. Connector account (child of connector, handles trading)
--   7. Connector stream (child of connector, handles pricing)
--   8. Pool and profile are assigned on the account and the stream
--      (POOL_ID / PROFILE_ID columns on XCORE_CONNECTOR_ACCOUNTS /
--      XCORE_CONNECTOR_STREAMS), customising trading, pricing, profit
--      and markup independently.
--
-- Also: XCore symbol -> MT4 symbol mapping (one to many per connector,
-- e.g. XCore EURUSD -> MT4 EURUSD.retail and EURUSD.prime).
--
-- Trade tables (ORDER, ORDER_MT4, LEG, DEAL), giveups and the config
-- audit log are deliberately left out of this file; they depend on
-- decisions (VALUE format, matching semantics, audit granularity) Josh
-- hasn't settled yet. Config rows below are filled in by Josh.
--
-- Run as: mysql -u root -p xcore < xcore_config.sql

USE xcore;

-- ---------------------------------------------------------------------------
-- 1. Providers: PrimeXM makers, one row per liquidity provider.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_PROVIDERS (
    PROVIDER_ID     INT          NOT NULL AUTO_INCREMENT,
    NAME            VARCHAR(32)  NOT NULL,          -- e.g. saxo
    FIX_HOST        VARCHAR(64)  NOT NULL DEFAULT '',
    FIX_PORT        INT          NOT NULL DEFAULT 0,
    SENDER_COMP_ID  VARCHAR(32)  NOT NULL DEFAULT '',
    TARGET_COMP_ID  VARCHAR(32)  NOT NULL DEFAULT '',
    ENABLE          TINYINT      NOT NULL DEFAULT 1,
    PRIMARY KEY (PROVIDER_ID),
    UNIQUE KEY (NAME)
);

-- ---------------------------------------------------------------------------
-- 2. Provider symbol -> XCore symbol mapping. Many provider symbols can map
--    to one XCore symbol (e.g. Bank A EUR/USD and Bank B EURUSD.ecn both map
--    to XCore EURUSD).
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_PROVIDER_SYMBOLS (
    PROVIDER_ID      INT         NOT NULL,
    PROVIDER_SYMBOL  VARCHAR(32) NOT NULL,          -- e.g. EUR/USD, EURUSD.ecn
    XCORE_SYMBOL     VARCHAR(12) NOT NULL,          -- e.g. EURUSD
    PRIMARY KEY (PROVIDER_ID, PROVIDER_SYMBOL),
    FOREIGN KEY (PROVIDER_ID) REFERENCES XCORE_PROVIDERS (PROVIDER_ID)
);

-- ---------------------------------------------------------------------------
-- 3. Liquidity pools: the set of providers behind each XCore symbol, with a
--    priority order (e.g. primary vs. backup provider).
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_LIQUIDITY_POOLS (
    POOL_ID  INT          NOT NULL AUTO_INCREMENT,
    NAME     VARCHAR(32)  NOT NULL,
    PRIMARY KEY (POOL_ID),
    UNIQUE KEY (NAME)
);

CREATE TABLE XCORE_LIQUIDITY_POOL_PROVIDERS (
    POOL_ID       INT         NOT NULL,
    XCORE_SYMBOL  VARCHAR(12) NOT NULL,
    PROVIDER_ID   INT         NOT NULL,
    PRIORITY      INT         NOT NULL DEFAULT 0,   -- lower = preferred
    PRIMARY KEY (POOL_ID, XCORE_SYMBOL, PROVIDER_ID),
    FOREIGN KEY (POOL_ID) REFERENCES XCORE_LIQUIDITY_POOLS (POOL_ID),
    FOREIGN KEY (PROVIDER_ID) REFERENCES XCORE_PROVIDERS (PROVIDER_ID)
);

-- ---------------------------------------------------------------------------
-- 4. Profiles: XCore-level markup and commission (see domain-notes.md,
--    "Markup: lives in several places" -- this is layer 1 of 3).
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_PROFILES (
    PROFILE_ID       INT          NOT NULL AUTO_INCREMENT,
    NAME             VARCHAR(32)  NOT NULL,
    MARKUP_BID       DOUBLE       NOT NULL DEFAULT 0,  -- points subtracted from bid
    MARKUP_ASK       DOUBLE       NOT NULL DEFAULT 0,  -- points added to ask
    COMMISSION       DOUBLE       NOT NULL DEFAULT 0,
    COMMISSION_TYPE  TINYINT      NOT NULL DEFAULT 0,  -- 0 money, 1 pips, 2 percent
    PRIMARY KEY (PROFILE_ID),
    UNIQUE KEY (NAME)
);

-- ---------------------------------------------------------------------------
-- 5. Connectors: PrimeXM takers, the connection to a client system. One
--    connector per MT4 server.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_CONNECTORS (
    CONNECTOR_ID  INT          NOT NULL AUTO_INCREMENT,
    NAME          VARCHAR(32)  NOT NULL,            -- e.g. mt4_uk
    MT4_SERVER    VARCHAR(16)  NOT NULL,            -- MT4_USERS.SERVER, e.g. trade/mt4
    ENABLE        TINYINT      NOT NULL DEFAULT 1,
    PRIMARY KEY (CONNECTOR_ID),
    UNIQUE KEY (MT4_SERVER)
);

-- ---------------------------------------------------------------------------
-- XCore symbol -> MT4 symbol mapping (one to many per connector): e.g. XCore
-- EURUSD maps to MT4 EURUSD.retail and EURUSD.prime on the same connector.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_CONNECTOR_SYMBOLS (
    CONNECTOR_ID  INT         NOT NULL,
    XCORE_SYMBOL  VARCHAR(12) NOT NULL,
    MT4_SYMBOL    VARCHAR(16) NOT NULL,              -- MT4_SYMBOLS.SYMBOL
    PRIMARY KEY (CONNECTOR_ID, XCORE_SYMBOL, MT4_SYMBOL),
    FOREIGN KEY (CONNECTOR_ID) REFERENCES XCORE_CONNECTORS (CONNECTOR_ID)
);

-- ---------------------------------------------------------------------------
-- 6. Connector account (child of connector): handles trading. Exactly one
--    per connector (per MT4 server).
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_CONNECTOR_ACCOUNTS (
    CONNECTOR_ID  INT  NOT NULL,
    POOL_ID       INT  NULL,
    PROFILE_ID    INT  NULL,
    PRIMARY KEY (CONNECTOR_ID),
    FOREIGN KEY (CONNECTOR_ID) REFERENCES XCORE_CONNECTORS (CONNECTOR_ID),
    FOREIGN KEY (POOL_ID) REFERENCES XCORE_LIQUIDITY_POOLS (POOL_ID),
    FOREIGN KEY (PROFILE_ID) REFERENCES XCORE_PROFILES (PROFILE_ID)
);

-- ---------------------------------------------------------------------------
-- 7. Connector stream (child of connector): handles pricing. Exactly one
--    per connector.
-- ---------------------------------------------------------------------------
CREATE TABLE XCORE_CONNECTOR_STREAMS (
    CONNECTOR_ID  INT  NOT NULL,
    POOL_ID       INT  NULL,
    PROFILE_ID    INT  NULL,
    PRIMARY KEY (CONNECTOR_ID),
    FOREIGN KEY (CONNECTOR_ID) REFERENCES XCORE_CONNECTORS (CONNECTOR_ID),
    FOREIGN KEY (POOL_ID) REFERENCES XCORE_LIQUIDITY_POOLS (POOL_ID),
    FOREIGN KEY (PROFILE_ID) REFERENCES XCORE_PROFILES (PROFILE_ID)
);
