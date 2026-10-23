-- XCore configuration rows Josh has defined so far.
-- FIX comp IDs are invented: sender = the bridge's side, target = the bank.

INSERT INTO xcore.XCORE_PROVIDERS (PROVIDER_ID, NAME, SENDER_COMP_ID, TARGET_COMP_ID, ENABLE) VALUES
  (1, 'BankA',      'TASMAN_XC_BANKA',     'BANKA_FX',  1),
  (2, 'BankAToxic', 'TASMAN_XC_BANKA_TOX', 'BANKA_FX',  1),
  (3, 'BankB',      'TASMAN_XC_BANKB',     'BANKB_ECN', 1),
  (4, 'BankBToxic', 'TASMAN_XC_BANKB_TOX', 'BANKB_ECN', 1);

INSERT INTO xcore.XCORE_SYMBOLS (SYMBOL, TYPE, CCY1, CCY2) VALUES
  ('EUR/USD', 'FX',  'EUR',    'USD'),
  ('GBP/USD', 'FX',  'GBP',    'USD'),
  ('AUD/USD', 'FX',  'AUD',    'USD'),
  ('NZD/USD', 'FX',  'NZD',    'USD'),
  ('USD/JPY', 'FX',  'USD',    'JPY'),
  ('USD/CHF', 'FX',  'USD',    'CHF'),
  ('USD/CAD', 'FX',  'USD',    'CAD'),
  ('EUR/GBP', 'FX',  'EUR',    'GBP'),
  ('EUR/JPY', 'FX',  'EUR',    'JPY'),
  ('GBP/JPY', 'FX',  'GBP',    'JPY'),
  ('AUD/JPY', 'FX',  'AUD',    'JPY'),
  ('CAD/JPY', 'FX',  'CAD',    'JPY'),
  ('EUR/CHF', 'FX',  'EUR',    'CHF'),
  ('XAU/USD', 'FX',  'XAU',    'USD'),
  ('XAG/USD', 'FX',  'XAG',    'USD'),
  ('WTI',     'CFD', 'USOIL',  'USD'),
  ('Brent',   'CFD', 'UKOIL',  'USD'),
  ('Nasdaq',  'CFD', 'NAS100', 'USD'),
  ('SP500',   'CFD', 'SP500',  'USD');

INSERT INTO xcore.XCORE_LIQUIDITY_POOLS (POOL_ID, NAME) VALUES
  (1, 'Bank_FX'),
  (2, 'Toxic_FX');

-- Default providers. Later changes go through fxgen/pools.py, which logs them.
INSERT INTO xcore.XCORE_LIQUIDITY_POOL_PROVIDERS (POOL_ID, XCORE_SYMBOL, PROVIDER_ID) VALUES
  (1, 'EUR/USD', '1,3'), (1, 'GBP/USD', '1,3'), (1, 'AUD/USD', '1,3'), (1, 'NZD/USD', '1,3'),
  (1, 'USD/JPY', '1,3'), (1, 'USD/CHF', '1,3'), (1, 'USD/CAD', '1,3'), (1, 'EUR/GBP', '1,3'),
  (1, 'EUR/JPY', '1,3'), (1, 'GBP/JPY', '1,3'), (1, 'AUD/JPY', '1,3'), (1, 'CAD/JPY', '1,3'),
  (1, 'EUR/CHF', '1,3'), (1, 'XAU/USD', '1,3'), (1, 'XAG/USD', '1,3'),
  (1, 'WTI',     '1'),   (1, 'Brent',   '1'),   (1, 'Nasdaq',  '1'),   (1, 'SP500',   '1'),
  (2, 'EUR/USD', '2,4'), (2, 'GBP/USD', '2,4'), (2, 'AUD/USD', '2,4'), (2, 'NZD/USD', '2,4'),
  (2, 'USD/JPY', '2,4'), (2, 'USD/CHF', '2,4'), (2, 'USD/CAD', '2,4'), (2, 'EUR/GBP', '2,4'),
  (2, 'EUR/JPY', '2,4'), (2, 'GBP/JPY', '2,4'), (2, 'AUD/JPY', '2,4'), (2, 'CAD/JPY', '2,4'),
  (2, 'EUR/CHF', '2,4'), (2, 'XAU/USD', '2,4'), (2, 'XAG/USD', '2,4'),
  (2, 'WTI',     '1'),   (2, 'Brent',   '1'),   (2, 'Nasdaq',  '1'),   (2, 'SP500',   '1');

INSERT INTO xcore.XCORE_CONNECTORS (CONNECTOR_ID, NAME, DESCRIPTION) VALUES
  (1, 'trade/mt4',        'connector for mt4 server'),
  (2, 'trade/uk_cov_100', 'giveup to login 100'),
  (3, 'trade/uk_cov_200', 'giveup to login 200'),
  (4, 'trade/nz_cov_300', 'giveup to login 300'),
  (5, 'trade/nz_cov_400', 'giveup to login 400');

-- Pool 1 = Bank_FX. Profiles: 1 Retail, 2 B2B, 3 WL, 4 Toxic, 5 House.
-- `GROUP`, LOGIN, LEAD_SOURCE: comma-separated lists, * = anything, NULL = nothing.
INSERT INTO xcore.XCORE_CONNECTOR_ACCOUNTS
  (ACCOUNT_ID, CONNECTOR_ID, NAME, `GROUP`, LOGIN, LEAD_SOURCE, POOL_ID, PROFILE_ID) VALUES
  (1, 1, 'Retail',     'RetailUSD,RetailEUR,RetailJPY,RetailGBP', '*',   '*',  1, 1),
  (2, 1, 'B2B',        'B2B',                                     '*',   '*',  1, 2),
  (3, 1, 'WL',         'White Label',                             '*',   'WL', 1, 3),
  (4, 1, 'Toxic',      NULL,                                      NULL,  NULL, 1, 4),
  (5, 1, 'House',      'House',                                   '20,50', '*', 1, 5),
  (6, 2, 'uk_cov_100', '*',                                       '100', '*',  1, 2),
  (7, 3, 'uk_cov_200', '*',                                       '200', '*',  1, 2),
  (8, 4, 'nz_cov_300', '*',                                       '300', '*',  1, 2),
  (9, 5, 'nz_cov_400', '*',                                       '400', '*',  1, 2);

INSERT INTO xcore.XCORE_PROFILES (PROFILE_ID, NAME) VALUES
  (1, 'Retail'),
  (2, 'B2B'),
  (3, 'WL'),
  (4, 'Toxic'),
  (5, 'House');

-- Pool and XCore markup per profile and symbol, in price units. Later changes
-- go through fxgen/profiles.py, which logs them.
INSERT INTO xcore.XCORE_PROFILE_SYMBOLS (PROFILE_ID, XCORE_SYMBOL, POOL_ID, MARKUP_BID, MARKUP_ASK) VALUES
  (1, 'EUR/USD', 1, -0.00002, 0.00002),
  (1, 'GBP/USD', 1, -0.00005, 0.00005),
  (1, 'AUD/USD', 1, -0.00003, 0.00003),
  (1, 'NZD/USD', 1, -0.00003, 0.00003),
  (1, 'USD/JPY', 1,   -0.005,   0.005),
  (1, 'USD/CHF', 1, -0.00002, 0.00002),
  (1, 'USD/CAD', 1, -0.00003, 0.00003),
  (1, 'EUR/GBP', 1, -0.00002, 0.00002),
  (1, 'EUR/JPY', 1,   -0.005,   0.005),
  (1, 'GBP/JPY', 1,   -0.005,   0.005),
  (1, 'AUD/JPY', 1,   -0.005,   0.005),
  (1, 'CAD/JPY', 1,   -0.005,   0.005),
  (1, 'EUR/CHF', 1, -0.00003, 0.00003),
  (1, 'XAU/USD', 1,        0,       0),
  (1, 'XAG/USD', 1,        0,       0),
  (1, 'WTI',     1,        0,       0),
  (1, 'Brent',   1,        0,       0),
  (1, 'Nasdaq',  1,        0,       0),
  (1, 'SP500',   1,        0,       0),
  (2, 'EUR/USD', 1,        0,       0),
  (2, 'GBP/USD', 1, -0.00001, 0.00001),
  (2, 'AUD/USD', 1, -0.00001, 0.00001),
  (2, 'NZD/USD', 1, -0.00001, 0.00001),
  (2, 'USD/JPY', 1,   -0.002,   0.002),
  (2, 'USD/CHF', 1,        0,       0),
  (2, 'USD/CAD', 1, -0.00002, 0.00002),
  (2, 'EUR/GBP', 1,        0,       0),
  (2, 'EUR/JPY', 1,   -0.002,   0.002),
  (2, 'GBP/JPY', 1,   -0.002,   0.002),
  (2, 'AUD/JPY', 1,   -0.002,   0.002),
  (2, 'CAD/JPY', 1,   -0.002,   0.002),
  (2, 'EUR/CHF', 1, -0.00001, 0.00001),
  (2, 'XAU/USD', 1,        0,       0),
  (2, 'XAG/USD', 1,        0,       0),
  (2, 'WTI',     1,        0,       0),
  (2, 'Brent',   1,        0,       0),
  (2, 'Nasdaq',  1,        0,       0),
  (2, 'SP500',   1,        0,       0),
  (3, 'EUR/USD', 1, -0.00005, 0.00005),
  (3, 'GBP/USD', 1, -0.00007, 0.00007),
  (3, 'AUD/USD', 1, -0.00007, 0.00007),
  (3, 'NZD/USD', 1, -0.00007, 0.00007),
  (3, 'USD/JPY', 1,   -0.008,   0.008),
  (3, 'USD/CHF', 1, -0.00005, 0.00005),
  (3, 'USD/CAD', 1, -0.00003, 0.00003),
  (3, 'EUR/GBP', 1, -0.00007, 0.00007),
  (3, 'EUR/JPY', 1,   -0.008,   0.008),
  (3, 'GBP/JPY', 1,   -0.008,   0.008),
  (3, 'AUD/JPY', 1,   -0.008,   0.008),
  (3, 'CAD/JPY', 1,   -0.008,   0.008),
  (3, 'EUR/CHF', 1, -0.00007, 0.00007),
  (3, 'XAU/USD', 1,    -0.05,    0.05),
  (3, 'XAG/USD', 1,    -0.03,    0.03),
  (3, 'WTI',     1,    -0.02,    0.02),
  (3, 'Brent',   1,    -0.02,    0.02),
  (3, 'Nasdaq',  1,    -0.02,    0.02),
  (3, 'SP500',   1,    -0.02,    0.02),
  (4, 'EUR/USD', 2, -0.00005, 0.00005),
  (4, 'GBP/USD', 2, -0.00007, 0.00007),
  (4, 'AUD/USD', 2, -0.00007, 0.00007),
  (4, 'NZD/USD', 2, -0.00007, 0.00007),
  (4, 'USD/JPY', 2,   -0.008,   0.008),
  (4, 'USD/CHF', 2, -0.00005, 0.00005),
  (4, 'USD/CAD', 2, -0.00003, 0.00003),
  (4, 'EUR/GBP', 2, -0.00007, 0.00007),
  (4, 'EUR/JPY', 2,   -0.008,   0.008),
  (4, 'GBP/JPY', 2,   -0.008,   0.008),
  (4, 'AUD/JPY', 2,   -0.008,   0.008),
  (4, 'CAD/JPY', 2,   -0.008,   0.008),
  (4, 'EUR/CHF', 2, -0.00007, 0.00007),
  (4, 'XAU/USD', 2,        0,       0),
  (4, 'XAG/USD', 2,        0,       0),
  (4, 'WTI',     2,        0,       0),
  (4, 'Brent',   2,        0,       0),
  (4, 'Nasdaq',  2,        0,       0),
  (4, 'SP500',   2,        0,       0),
  (5, 'EUR/USD', 1,        0,       0),
  (5, 'GBP/USD', 1,        0,       0),
  (5, 'AUD/USD', 1,        0,       0),
  (5, 'NZD/USD', 1,        0,       0),
  (5, 'USD/JPY', 1,        0,       0),
  (5, 'USD/CHF', 1,        0,       0),
  (5, 'USD/CAD', 1,        0,       0),
  (5, 'EUR/GBP', 1,        0,       0),
  (5, 'EUR/JPY', 1,        0,       0),
  (5, 'GBP/JPY', 1,        0,       0),
  (5, 'AUD/JPY', 1,        0,       0),
  (5, 'CAD/JPY', 1,        0,       0),
  (5, 'EUR/CHF', 1,        0,       0),
  (5, 'XAU/USD', 1,        0,       0),
  (5, 'XAG/USD', 1,        0,       0),
  (5, 'WTI',     1,        0,       0),
  (5, 'Brent',   1,        0,       0),
  (5, 'Nasdaq',  1,        0,       0),
  (5, 'SP500',   1,        0,       0);

-- Giveup rules, values verbatim as XCore holds them.
INSERT INTO xcore.XCORE_GIVEUPS (GIVEUP_ID, CONNECTOR, ACCOUNT, SYMBOL, `GROUP`, LOGIN, LEAD_SOURCE, BOOK, TARGET) VALUES
  (1, 'trade/mt4',        '*',          '*', '*',           '*', '*',          'b_only', 10),
  (2, 'trade/mt4',        '*',          '*', '*',           '*', 'NZ_*',       'any',    30),
  (3, 'trade/mt4',        '*',          '*', '*',           '*', 'UK_*, NZ_*', 'any',    40),
  (4, 'trade/mt4',        '*',          '*', 'White Label', '*', '*',          'any',    100000),
  (5, 'trade/uk_cov_100', 'uk_cov_100', '*', '*',           '*', '*',          '*',      100),
  (6, 'trade/uk_cov_200', 'uk_cov_200', '*', '*',           '*', '*',          '*',      200),
  (7, 'trade/nz_cov_300', 'nz_cov_300', '*', '*',           '*', '*',          '*',      300),
  (8, 'trade/nz_cov_400', 'nz_cov_400', '*', '*',           '*', '*',          '*',      400);
