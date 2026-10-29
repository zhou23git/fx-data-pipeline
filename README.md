# fx-data-pipeline

A recreation of an FX broker's data system (MT4 trading platform, PrimeXM
XCore bridge, liquidity providers) with fake data, built to learn Snowflake
and dbt on realistic, messy sources.

## Status

| Part | State |
|---|---|
| `mysql/mt4_config.sql`: MT4 config and account tables for the local `mt4` schema | Ready |
| `mysql/mt4_seed.sql`: MT4 config rows and one-off accounts | In progress |
| `mysql/mt4_trades.sql`: MT4 trades table (tickets, plus balance and credit rows) | Ready |
| `mysql/mt4_prices.sql`: MT4 prices table (latest quote per symbol, the end-of-day snapshot) | Ready |
| `mysql/xcore_config.sql`: XCore config tables and config audit log for the `xcore` schema | Ready |
| `mysql/xcore_seed.sql`: providers, XCore symbols, liquidity pools, profiles | In progress |
| `fxgen/accounts.py`: creates retail accounts in MySQL, run daily | Ready |
| `fxgen/pools.py`: adds or drops providers in liquidity pools and sets connector accounts' pools, logging each change | Ready; random mode waits on rules |
| `mysql/xcore_trades.sql`: XCore order, order MT4 and leg tables | Ready |
| `fxgen/orders.py`: simulates MT4 -> XCore executions; `sample` writes 10 showcase trade sets | First version, under review |
| `fxgen/mt4trades.py`: MT4 tickets: open, close, close by hedge, giveup booking, deposits and withdrawals | First version |
| `fxgen/hourly.py`: the hourly process, one simulated hour of direct and API trading per run | First version; writes the end-of-day price snapshot on the 16:55 New York run |
| `fxgen/prices.py`: fake end-of-day prices in MT4_PRICES | First version |
| `fxgen/profiles.py`: sets profile markup and pool per symbol, plus random daily markup, logging each change | Ready |
| `fxgen/`: trade data generator | Work in progress, not runnable yet; will be adapted to read config from MySQL |
| Snowflake and dbt | Not started |

## Plan

1. Configuration: MT4 and XCore config tables and accounts in local MySQL.
2. Generate trading data (MT4 trades, XCore orders and legs, giveup copies,
   config audit log) against that configuration.
3. Load into Snowflake; model with dbt.

How the real system worked is in [docs/domain-notes.md](docs/domain-notes.md).
