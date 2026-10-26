-- Simulated PrimeXM MT4 bridge. The real bridge is an MT4 plugin that routes
-- logins to XCore connector accounts. Only connector 1 (trade/mt4) takes
-- trades from MT4; the giveup connectors are clients sending FIX straight to
-- XCore. Here each trade/mt4 connector account's `GROUP`,
-- LOGIN and LEAD_SOURCE patterns (XCore style: * wildcard, ! negation,
-- comma-separated lists) are turned into regexes and matched against every
-- tradeable MT4 login and symbol.
--
-- Run:  CALL reference.connector_account_login();
-- Out:  reference.connector_account_logins, one row per connector account,
--       login and symbol.

-- ---------------------------------------------------------------------------
-- Pattern -> regex. '!EURUSD,!GBP*,SP500,*JPY' gives
--   pattern_pos_re = ^(SP500|.*JPY)$     pattern_neg_re = ^(EURUSD|GBP.*)$
-- A value matches when it matches pos and doesn't match neg (neg NULL = none).
-- NULL pattern -> NULL regex -> matches nothing.
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS reference.pattern_pos_re;
DROP FUNCTION IF EXISTS reference.pattern_neg_re;

DELIMITER //

CREATE FUNCTION reference.pattern_pos_re(pattern VARCHAR(255)) RETURNS VARCHAR(1024)
DETERMINISTIC NO SQL
BEGIN
    DECLARE s, pos VARCHAR(1024);
    SET s = CONCAT(',', REGEXP_REPLACE(TRIM(pattern), '\\s*,\\s*', ','));
    SET pos = TRIM(BOTH ',' FROM REGEXP_REPLACE(s, ',![^,]*', ''));
    RETURN CONCAT('^(', REPLACE(REPLACE(REPLACE(pos, '.', '\\.'), '*', '.*'), ',', '|'), ')$');
END //

CREATE FUNCTION reference.pattern_neg_re(pattern VARCHAR(255)) RETURNS VARCHAR(1024)
DETERMINISTIC NO SQL
BEGIN
    DECLARE s, neg VARCHAR(1024);
    SET s = CONCAT(',', REGEXP_REPLACE(TRIM(pattern), '\\s*,\\s*', ','));
    SET neg = REPLACE(TRIM(BOTH ',' FROM REGEXP_REPLACE(s, ',[^!,][^,]*', '')), '!', '');
    RETURN IF(neg = '', NULL, CONCAT('^(', REPLACE(REPLACE(REPLACE(neg, '.', '\\.'), '*', '.*'), ',', '|'), ')$'));
END //

DELIMITER ;

-- ---------------------------------------------------------------------------
-- Output table, rebuilt by each run.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference.connector_account_logins (
    CONNECTOR          VARCHAR(32)   NOT NULL,
    CONNECTOR_ACCOUNT  VARCHAR(32)   NOT NULL,
    POOL_ID            INT           NOT NULL,
    PROFILE_ID         INT           NOT NULL,
    LOGIN              INT           NOT NULL,
    `GROUP`            VARCHAR(16)   NOT NULL,
    LEAD_SOURCE        VARCHAR(32)   NOT NULL,
    AGENT_ACCOUNT      INT           NOT NULL,
    ACCOUNT_CURRENCY   VARCHAR(12)   NULL,
    SYMBOL             VARCHAR(16)   NOT NULL,
    SPREAD_DIFF        INT           NOT NULL,
    COMM_BASE          INT           NOT NULL,
    LOT_MIN            DECIMAL(8,2)  NOT NULL,
    LOT_MAX            DECIMAL(8,2)  NOT NULL,
    LOT_STEP           DECIMAL(8,2)  NOT NULL,
    PRIMARY KEY (CONNECTOR, CONNECTOR_ACCOUNT, LOGIN, SYMBOL),
    INDEX (LOGIN, SYMBOL)
);

-- ---------------------------------------------------------------------------
-- The bridge.
-- ---------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS reference.connector_account_login;

DELIMITER //

CREATE PROCEDURE reference.connector_account_login()
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE conn, acct VARCHAR(32);
    DECLARE grp, mt4_login, lead_src VARCHAR(255);
    DECLARE pool, prof INT;
    DECLARE bridge CURSOR FOR
        SELECT a.`NAME` AS connector, b.`NAME` AS connector_account, b.`GROUP`, b.LOGIN, b.LEAD_SOURCE, b.POOL_ID, b.PROFILE_ID
        FROM xcore.xcore_connectors a
        JOIN xcore.xcore_connector_accounts b
        ON a.connector_id = b.connector_id
        WHERE a.connector_id = 1  -- trade/mt4 only: the other connectors are FIX clients, not MT4 trading
        ORDER BY b.ACCOUNT_ID;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    -- Every MT4 login that can trade, with each symbol its group can trade.
    drop temporary table if exists reference.trading_logins;

    create temporary table reference.trading_logins
	(index(login,`group`,lead_source))
		select LOGIN, user_symbol.`GROUP`, LEAD_SOURCE, AGENT_ACCOUNT, CURRENCY as ACCOUNT_CURRENCY, SYMBOL, SPREAD_DIFF, COMM_BASE, LOT_MIN, LOT_MAX, LOT_STEP
		from (
			select *
			from (
				select LOGIN, a.`GROUP`, LEAD_SOURCE, AGENT_ACCOUNT, b.CURRENCY
				from mt4.mt4_users a
				left join MT4.mt4_groups b
				on a.`server` = b.`server`
				and a.`group` = b.`group`
			) users
			join (
				SELECT b.name as INSTRUMENT, b.sec_index, a.symbol
				FROM mt4.mt4_symbols a
				left join mt4.mt4_securities b
				on b.server = 'trade/mt4'
				and a.type = b.sec_index
			) symbols
		) user_symbol
		join mt4.mt4_group_securities group_sec
		on group_sec.server = 'trade/mt4'
		and group_sec.group = user_symbol.group
		and group_sec.sec_index = user_symbol.sec_index
		where LEAD_SOURCE IS NOT NULL
		AND LEAD_SOURCE <> ''
		order by 1, 6;

    TRUNCATE TABLE reference.connector_account_logins;

    -- Fixed text, prepared once: each account's values arrive through ?, so
    -- no pattern text is ever spliced into SQL.
    SET @bridge_sql =
        'INSERT INTO reference.connector_account_logins
         SELECT ?, ?, ?, ?, t.LOGIN, t.`GROUP`, t.LEAD_SOURCE, t.AGENT_ACCOUNT, t.ACCOUNT_CURRENCY,
                t.SYMBOL, t.SPREAD_DIFF, t.COMM_BASE, t.LOT_MIN, t.LOT_MAX, t.LOT_STEP
         FROM reference.trading_logins t
         WHERE t.`GROUP` REGEXP ? AND (? IS NULL OR t.`GROUP` NOT REGEXP ?)
           AND CAST(t.LOGIN AS CHAR) REGEXP ? AND (? IS NULL OR CAST(t.LOGIN AS CHAR) NOT REGEXP ?)
           AND t.LEAD_SOURCE REGEXP ? AND (? IS NULL OR t.LEAD_SOURCE NOT REGEXP ?)';
    PREPARE stmt FROM @bridge_sql;

    OPEN bridge;
    read_loop: LOOP
        FETCH bridge INTO conn, acct, grp, mt4_login, lead_src, pool, prof;
        IF done THEN
            LEAVE read_loop;
        END IF;
        SET @conn = conn, @acct = acct, @pool = pool, @prof = prof,
            @grp_pos = reference.pattern_pos_re(grp), @grp_neg = reference.pattern_neg_re(grp),
            @login_pos = reference.pattern_pos_re(mt4_login), @login_neg = reference.pattern_neg_re(mt4_login),
            @ls_pos = reference.pattern_pos_re(lead_src), @ls_neg = reference.pattern_neg_re(lead_src);
        EXECUTE stmt USING @conn, @acct, @pool, @prof,
            @grp_pos, @grp_neg, @grp_neg,
            @login_pos, @login_neg, @login_neg,
            @ls_pos, @ls_neg, @ls_neg;
    END LOOP;
    CLOSE bridge;

    DEALLOCATE PREPARE stmt;
END //

DELIMITER ;
