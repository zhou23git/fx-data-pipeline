# Notes for Claude

- Read `docs/domain-notes.md` before changing schemas or the generator. It
  records how the real MT4/XCore system worked, as Josh explained it. Add to it
  whenever he explains more.
- Josh drives the design: configuration tables first, in local MySQL schemas
  `mt4` and `xcore`. He fills config tables himself; give him SQL to run unless
  this session can reach his MySQL.
- MT4 server name used in data: `trade/mt4`.
- `fxgen/` is unfinished and currently uses hard-coded reference data. It should
  end up reading the configuration from MySQL.
- Prefer tables over ASCII diagrams in explanations.
