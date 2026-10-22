# fx-data-pipeline

A recreation of an FX broker's data system (MT4 trading platform, PrimeXM
XCore bridge, liquidity providers) with fake data, built to learn Snowflake
and dbt on realistic, messy sources.

## Status

| Part | State |
|---|---|
| `mysql/mt4_config.sql`: MT4 config and account tables for the local `mt4` schema | Ready |
| `mysql/mt4_seed.sql`: MT4 config rows and one-off accounts | In progress |
| `mysql/xcore_config.sql`: XCore config tables for the `xcore` schema | Tables created, not filled |
| `fxgen/accounts.py`: creates retail accounts in MySQL, run daily | Ready |
| `fxgen/`: trade data generator | Work in progress, not runnable yet; will be adapted to read config from MySQL |
| Snowflake and dbt | Not started |

## Plan

1. Configuration: MT4 and XCore config tables and accounts in local MySQL.
2. Generate trading data (MT4 trades, XCore orders and legs, giveup copies,
   config audit log) against that configuration.
3. Load into Snowflake; model with dbt.

How the real system worked is in [docs/domain-notes.md](docs/domain-notes.md).
