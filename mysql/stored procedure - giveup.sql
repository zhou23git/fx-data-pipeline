-- Simulated XCore giveups. XCore sends a drop copy of every matching
-- execution to the MT4 coverage login in each giveup rule's TARGET; the copies
-- exist only in MT4, without the detail reporting needs. This rebuilds them
-- with full detail: each XCORE_GIVEUPS rule, in GIVEUP_ID order, has its
-- patterns (XCore style: * wildcard, ! negation, comma lists) turned into
-- regexes and matched against the order / leg rows. Every
-- matching rule produces a copy, so one execution can go to several targets.
--
-- Needs reference.pattern_pos_re and reference.pattern_neg_re
-- (stored procedure - connector account login.sql).
--
-- Run:  CALL reporting.giveup();
-- Out:  reporting.giveup_trades, one row per filled leg and matching rule.

CREATE DATABASE IF NOT EXISTS reporting;

-- ---------------------------------------------------------------------------
-- Output table, rebuilt by each run.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS reporting.giveup_trades;

CREATE TABLE reporting.giveup_trades (
    ORDER_ID             BIGINT         NOT NULL,
    CONNECTOR            VARCHAR(32)    NOT NULL,
    ACCOUNT              VARCHAR(32)    NOT NULL,
    SYMBOL               VARCHAR(12)    NOT NULL,   -- XCore symbol
    SIDE                 VARCHAR(4)     NOT NULL,
    SUBID1               INT            NULL,       -- login
    SUBID2               BIGINT         NULL,       -- CLORDID
    SUBID3               VARCHAR(16)    NULL,       -- group
    SUBID4               VARCHAR(32)    NULL,       -- lead source
    OrderFillPrice       DECIMAL(24,12) NOT NULL,
    LEG_ID               INT            NOT NULL,
    B_BOOK               TINYINT        NOT NULL,
    LP                   INT            NOT NULL,
    MARKUP_BID           DECIMAL(10,5)  NOT NULL,
    MARKUP_ASK           DECIMAL(10,5)  NOT NULL,
    LegFillSize          DECIMAL(20,6)  NOT NULL,
    FILLPRICE1           DECIMAL(18,6)  NOT NULL,
    FILLPRICE2           DECIMAL(18,6)  NOT NULL,
    GIVEUP_ID            INT            NOT NULL,   -- rule that matched
    GIVEUP_LOGIN         INT            NOT NULL,   -- XCORE_GIVEUPS.TARGET: coverage login the copy goes to
    WITH_MARKUP          TINYINT        NOT NULL,
    GIVEUP_PRICE         DECIMAL(18,6)  NOT NULL,   -- OrderFillPrice when WITH_MARKUP = 1, leg FILLPRICE1 when 0; rounded in the broker's favour
    PRIMARY KEY (GIVEUP_ID, ORDER_ID, LEG_ID),
    INDEX (GIVEUP_LOGIN)
);

-- ---------------------------------------------------------------------------
-- The giveups.
-- ---------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS reporting.giveup;

DELIMITER //

CREATE PROCEDURE reporting.giveup()
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE g_id, g_target INT;
    DECLARE g_markup TINYINT;
    DECLARE g_conn, g_acct, g_sym, g_grp, g_login, g_ls VARCHAR(255);
    DECLARE g_book VARCHAR(32);
    DECLARE book_flag TINYINT;    -- leg B_BOOK the rule needs; NULL = any
    DECLARE conn_pos, conn_neg, acct_pos, acct_neg, sym_pos, sym_neg,
            grp_pos, grp_neg, login_pos, login_neg, ls_pos, ls_neg VARCHAR(1024);
    DECLARE rules CURSOR FOR
        SELECT GIVEUP_ID, CONNECTOR, ACCOUNT, SYMBOL, `GROUP`, LOGIN, LEAD_SOURCE, BOOK, TARGET, WITH_MARKUP
        FROM xcore.xcore_giveups
        ORDER BY GIVEUP_ID;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    -- Order / leg rows with the fields giveups match on (order MT4 isn't
    -- needed). Only filled legs: a rejected leg is never copied. Missing values become '' so that * still
    -- matches them (orders from FIX connectors have no MT4 subids).
    DROP TEMPORARY TABLE IF EXISTS reporting.order_leg_mt4;

    CREATE TEMPORARY TABLE reporting.order_leg_mt4
        SELECT ord.ORDER_ID, ord.CONNECTOR, ord.ACCOUNT, ord.SYMBOL, sym.digits,
               ord.SIDE, SUBID1, SUBID2, SUBID3, SUBID4,
               ord.FILLPRICE as OrderFillPrice,
               leg.LEG_ID, b_book, LP, Markup_Bid, Markup_Ask, leg.fillsize as LegFillSize, fillprice1, fillprice2,
               COALESCE(CAST(SUBID1 AS CHAR), '') AS match_login,
               COALESCE(SUBID3, '') AS match_group,
               COALESCE(SUBID4, '') AS match_lead_source
        FROM xcore.xcore_order ord
        left join reference.xcore_symbol_reference sym
        on ord.symbol = sym.xcore_symbol
        left join xcore.xcore_leg leg
        on ord.order_id = leg.order_id
        where leg.fillsize > 0;

    TRUNCATE TABLE reporting.giveup_trades;

    OPEN rules;
    read_loop: LOOP
        FETCH rules INTO g_id, g_conn, g_acct, g_sym, g_grp, g_login, g_ls, g_book, g_target, g_markup;
        IF done THEN
            LEAVE read_loop;
        END IF;

        -- BOOK is kept as XCore holds it: b_only, a_only, any, *.
        SET book_flag = CASE g_book WHEN 'b_only' THEN 1 WHEN 'a_only' THEN 0 ELSE NULL END;
        SET conn_pos  = reference.pattern_pos_re(g_conn),  conn_neg  = reference.pattern_neg_re(g_conn),
            acct_pos  = reference.pattern_pos_re(g_acct),  acct_neg  = reference.pattern_neg_re(g_acct),
            sym_pos   = reference.pattern_pos_re(g_sym),   sym_neg   = reference.pattern_neg_re(g_sym),
            grp_pos   = reference.pattern_pos_re(g_grp),   grp_neg   = reference.pattern_neg_re(g_grp),
            login_pos = reference.pattern_pos_re(g_login), login_neg = reference.pattern_neg_re(g_login),
            ls_pos    = reference.pattern_pos_re(g_ls),    ls_neg    = reference.pattern_neg_re(g_ls);

        -- Static SQL: the rule's values are plain variables, nothing is spliced in.
        INSERT INTO reporting.giveup_trades
              (ORDER_ID, CONNECTOR, ACCOUNT, SYMBOL, SIDE, SUBID1, SUBID2, SUBID3, SUBID4,
               OrderFillPrice, LEG_ID, B_BOOK, LP, MARKUP_BID, MARKUP_ASK, LegFillSize, FILLPRICE1, FILLPRICE2,
               GIVEUP_ID, GIVEUP_LOGIN, WITH_MARKUP, GIVEUP_PRICE)
        SELECT t.ORDER_ID, t.CONNECTOR, t.ACCOUNT, t.SYMBOL, t.SIDE, t.SUBID1, t.SUBID2, t.SUBID3, t.SUBID4,
               t.OrderFillPrice, t.LEG_ID, t.b_book, t.LP, t.Markup_Bid, t.Markup_Ask, t.LegFillSize, t.fillprice1, t.fillprice2,
               g_id AS GIVEUP_ID,
               g_target AS GIVEUP_LOGIN,
               g_markup AS WITH_MARKUP,
               -- Rounded to the symbol's digits in the broker's favour, as MT4
               -- does: buys up (ceiling), sells down (floor). Prices are
               -- positive, so TRUNCATE is the floor.
               IF(t.SIDE = 'buy',
                  TRUNCATE(t.raw_price, t.digits)
                      + IF(t.raw_price > TRUNCATE(t.raw_price, t.digits), CAST(POW(10, -t.digits) AS DECIMAL(10,6)), 0),
                  TRUNCATE(t.raw_price, t.digits)) AS GIVEUP_PRICE
        FROM (SELECT o.*, IF(g_markup = 1, o.OrderFillPrice, o.fillprice1) AS raw_price
              FROM reporting.order_leg_mt4 o) t
        WHERE (book_flag IS NULL OR t.b_book = book_flag)
          AND t.CONNECTOR         REGEXP conn_pos  AND (conn_neg  IS NULL OR t.CONNECTOR         NOT REGEXP conn_neg)
          AND t.ACCOUNT           REGEXP acct_pos  AND (acct_neg  IS NULL OR t.ACCOUNT           NOT REGEXP acct_neg)
          AND t.SYMBOL            REGEXP sym_pos   AND (sym_neg   IS NULL OR t.SYMBOL            NOT REGEXP sym_neg)
          AND t.match_group       REGEXP grp_pos   AND (grp_neg   IS NULL OR t.match_group       NOT REGEXP grp_neg)
          AND t.match_login       REGEXP login_pos AND (login_neg IS NULL OR t.match_login       NOT REGEXP login_neg)
          AND t.match_lead_source REGEXP ls_pos    AND (ls_neg    IS NULL OR t.match_lead_source NOT REGEXP ls_neg);
    END LOOP;
    CLOSE rules;

    DROP TEMPORARY TABLE reporting.order_leg_mt4;
END //

DELIMITER ;
