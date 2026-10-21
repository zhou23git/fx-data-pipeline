-- Configuration rows Josh has defined so far.

INSERT INTO mt4.MT4_SECURITIES (SERVER, SEC_INDEX, NAME, DESCRIPTION) VALUES
  ('trade/mt4', 1, 'FX',    'EURUSD, USDJPY, GBPUSD, USDCHF, AUDUSD, USDCAD, NZDUSD'),
  ('trade/mt4', 2, 'METAL', 'XAUUSD, XAGUSD'),
  ('trade/mt4', 3, 'CFD',   'USOIL, UKOIL, NAS100, SP500');
