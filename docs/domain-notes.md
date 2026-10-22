# Domain notes: how the real FX system worked

What Josh explained about the systems this project recreates, so later work
stays faithful to it. Where something below is a guess rather than his
explanation, it is marked **(assumed)**.

## Goal

Recreate the FX broker's data system with fake data, then learn to manage it
in Snowflake (standalone) and dbt. Order of work, as Josh decided:

1. Configuration first: MT4 and XCore config tables and accounts, in a local
   MySQL with two schemas, `mt4` and `xcore`. Josh fills config tables himself.
2. Then generate trading data against that configuration.
3. Then load into Snowflake and model with dbt.

## MT4

- One MT4 server = one database in reality. Here both servers share schema
  `mt4`, so every table has a `SERVER` column (Josh's server name: `trade/mt4`).
- Export tables: `MT4_USERS`, `MT4_TRADES`, `MT4_DAILY`, `MT4_PRICES`.
  Column lists were confirmed by Josh as correct or close enough.
- Config (not in the standard export, modelled on Manager API records):
  security groups, symbols, groups, group-per-security settings
  (`SPREAD_DIFF`, commission, lot limits; details below), group margins.
- Security groups as Josh defined them: 1 FX, 2 METAL, 3 CFD (USOIL, UKOIL,
  NAS100, SP500).
- Symbol price fields, as Josh used them:
  - `DIGITS`: decimal places in the price (5 for EURUSD, 3 for USDJPY).
  - `POINT`: the smallest price step, 1 / 10^`DIGITS` (0.00001 for EURUSD).
    `SPREAD_DIFF` is counted in points.
  - `TICK_SIZE`: always equal to `POINT` here (never coarser).
  - `TICK_VALUE`: used to mark **mini contracts**. Usually `TICK_VALUE` =
    `TICK_SIZE` (ratio 1). When they differ, usually on SP500 and NAS100, the
    symbol is a mini lot: `TICK_SIZE` 0.01 and `TICK_VALUE` 0.001 (Josh's
    recollection), a ratio of 0.1, so the trade earns 1/10th of the price
    move.
  - P/L = lots x `CONTRACT_SIZE` x (close or current price - open price) x
    conversion rate x (`TICK_VALUE` / `TICK_SIZE`). Sells use
    open - close.
- Symbols (`MT4_SYMBOLS`), cut down by Josh to description, currency, type,
  digits, point, contract size, tick size and value, and swaps:
  - 13 FX pairs, each in three versions: plain (`EURUSD`), `.retail` and
    `.b2b`. Josh chose `.retail` even though real MT4 caps symbols at 11
    characters, so `SYMBOL` is `VARCHAR(16)`.
  - Metals XAUUSD and XAGUSD (currency XAU / XAG, contract 100). CFDs USOIL
    and UKOIL (contract 10), NAS100 and SP500 (contract 1, mini). CFDs have
    currency USD.
  - Swaps are in points (MT4 swap type "points"). `SWAP_LONG` and
    `SWAP_SHORT` are set daily by a plugin, so the config leaves them NULL.
    Only FX has swaps enabled.
- Entities: Equiti separated entities with login ranges and dedicated MT4
  servers, not with the group's `COMPANY` field. Here there is one server, and
  login ranges simulate the entities.
- Groups, simplified by Josh to `SERVER`, `GROUP`, `CURRENCY`: RetailUSD,
  RetailGBP, RetailJPY, RetailEUR, B2B, Coverage, White Label.
- A client's company name goes on the login (`MT4_USERS.NAME`), not the group.
- Accounts (`MT4_USERS`), cut down by Josh to group, name, lead source, phone,
  comment, agent account and currency. `REGDATE` was kept as well so accounts
  made on different days can be told apart. Two entities, NZ and UK; the
  entity shows in `LEAD_SOURCE` (`NZ_TRD`, `UK_TRD`, `NZ_COV`, `UK_COV`, `WL`).

  | Logins | Group | What |
  |---|---|---|
  | 10-50 | House | NZ B-book giveup, NZ trading, NZ and UK all-client giveups, UK trading |
  | 100-400 | Coverage | Giveup copies of B2B clients (100, 200 UK; 300, 400 NZ) |
  | 500-900 | B2B | B2B MT4 clients (500, 600 UK; 700-900 NZ) |
  | 1000-8999 | RetailUSD/GBP/EUR/JPY | Retail clients, NZ_TRD. Made by `fxgen/accounts.py`: a batch at the start, then a few a day |
  | 9990-9999 | Rebate | IB partners (4 used). No more will be made |
  | 100000 | Coverage | White Label coverage |
  | 100001-100100 | White Label | White Label clients (15 used). No more will be made |

- Rebates: about 2.5% of new retail accounts pay a rebate, shown by
  `AGENT_ACCOUNT` = a Rebate login. New retail accounts keep being assigned to
  the existing Rebate logins at that rate.
- Group security settings (`MT4_GROUP_SECURITIES`), as Josh set them in MT4
  Administrator:
  - `SPREAD_DIFF`: an integer in points (the last priced decimal, a tenth of
    a pip on 5-digit FX). Josh works out the markup in price from the symbol's
    `POINT`. He doesn't remember it as the group markup; that label comes from
    how MT4 defines the field.
  - Table cut down by Josh to `SPREAD_DIFF`, `COMM_BASE` and lot limits per
    group and security group. `COMM_TYPE` and the agent (IB) commission
    columns were dropped.
  - Commission: Josh picked a numeric `COMM_TYPE` (mapping not remembered) and
    entered an integer `COMM_BASE`. The effect was a fixed USD amount per
    100,000 USD of notional. At 10: 1 lot EURUSD about $11, 1 lot USDCAD $10,
    1 lot CADJPY about $8.50, depending on the base currency's USD rate.
  - Commission is charged **at open only**, for both sides: when the trade
    opens, MT4 writes 2x the per-side commission into the `COMMISSION` field
    of the trade's `MT4_TRADES` row. There is no separate commission record.
  - Partial close pro-rates commission between the tickets. Partial close is
    complicated; it will be worked out later.
  - Conversion: `MT4_TRADES.CONV_RATE1` is the rate from the symbol's base
    currency to the deposit currency. Josh derives the quote-to-deposit rate
    from it and the symbol price. (At work he also used an end-of-day query
    of MT4 prices; the simulation uses `CONV_RATE1` instead.)
    Standard MT4 may define `CONV_RATE1`/`CONV_RATE2` as profit (quote)
    currency to deposit, with `MARGIN_RATE` for the base currency. Josh can't
    check this. The PrimeXM bridge may have overridden it, so the simulation
    keeps his definition: `CONV_RATE1` = base to deposit.
  - Two rates, both needed: `CONV_RATE1` at open and `CONV_RATE2` at close.
    Commission uses only `CONV_RATE1`, since it is charged at open.
  - Worked example, `COMM_BASE` 10, 1 lot EURUSD at about 1.10, USD account:
    notional 100,000 EUR = 110,000 USD, so $11 per side, and `COMMISSION` is
    -22.00 at open.
  - Because commission is linear in notional, `COMM_BASE` USD per 100,000 USD
    is the same as `COMM_BASE` deposit currency per 100,000 of deposit
    currency. So, per side: `COMM_BASE` x lots x `CONTRACT_SIZE` x
    `CONV_RATE1` / 100,000, in deposit currency, with no extra rate table.
  - `LOT_MIN` 0.01 and `LOT_MAX` 100, in lots: in config, 1 means 1 lot.
    Min 0.01 lets FX clients trade 1,000 units at a time.
  - Trades are different: `MT4_TRADES.VOLUME` is an integer in hundredths of
    a lot (0.01 lot = 1, 1 lot = 100). Josh's ELT gets units with
    `VOLUME` / 100 x `CONTRACT_SIZE`.
- MT4 quirks to keep: one row per ticket updated in place (`MODIFY_TIME`);
  open trades have `CLOSE_TIME = 1970-01-01`; `VOLUME` in hundredths of a lot;
  `CMD` 6 = balance operation with amount in `PROFIT`; partial close creates a
  new ticket (`from #` / `to #` comments); server time GMT+2/+3.

## XCore (PrimeXM bridge)

Josh's setup order, which is also the dependency order of the tables:

1. **Providers** (PrimeXM: makers): name, FIX connection specs.
2. **Provider symbol -> XCore symbol mapping.** Many to one: Bank A
   `EUR/USD` and Bank B `EURUSD.ecn` both map to XCore `EURUSD`.
3. **Liquidity pools**: the set of providers for each XCore symbol.
4. **Profiles**: markup, commission, etc.
5. **Connectors** (PrimeXM: takers): the connection to a client system. One
   connector per MT4 server.
6. **Connector account** (child of connector): handles trading. Exactly one
   per MT4 server.
7. **Connector stream** (child of connector): handles pricing.
8. Liquidity pool and liquidity profile are applied to the account and the
   stream, which customises pricing, trading, profit and markup.

- **XCore symbol -> MT4 symbol** is one to many: XCore `EURUSD` maps to MT4
  `EURUSD.retail` and `EURUSD.prime`.
- Pools and profiles *can* vary by session, client and ad-hoc terms, and can
  change on the fly. At Equiti they did not change, but the simulation will
  change them so there is history to rebuild.

### Trade tables

- `ORDER`: the trade request. Carries session, client and ad-hoc terms
  fields.
- `ORDER_MT4`: one-to-one extension of `ORDER` with MT4-specific information
  (login, group, ticket, MT4 fields).
- `LEG`: the message XCore sent to a provider. The A/B-book flag lives here,
  as field `b_book`.
- `DEAL`: the provider's response. Not needed for this project.
- Josh's reporting join: `ORDER LEFT JOIN LEG LEFT JOIN DEAL`.
- Where A/B-book was decided in config: Josh doesn't remember. Only the
  `b_book` result on `LEG` matters. **(The routing rule table is assumed.)**

### Markup: lives in several places

Client price = provider price + XCore markup + giveup markup (where used) +
MT4 group markup.

1. XCore markup, bid and ask: part of the liquidity profile.
2. Giveup markup: set on the giveup (below).
3. MT4 group markup: `SPREAD_DIFF` on the MT4 group's security settings.

Working out which markup applied to which trade was a real puzzle at work,
which is why the simulation keeps all three.

### Giveups and coverage accounts

- A giveup is a **drop copy**: a copy of the client's trade sent to a coverage
  MT4 login. Without it, a trade exists only on the client login that
  placed it.
- Purpose: let MT4 serve as both the client platform and the broker's back
  office. The business can't add up hundreds of client accounts in SQL, but a
  coverage login shows net open position by business. Example: all retail to
  login 70000, all B2B to login 70001.
- Giveup trades exist **only in MT4** on the coverage login, never in XCore,
  and they lack the detail needed for reporting.
- **Giveup markup** splits markup between entities. When one trade is owned by
  two entities, each gets a coverage copy with different markups:
  - Simple split: coverage 1 gets a copy with no markups, coverage 2 gets a
    copy with only the XCore markup. Coverage 1 earns the XCore markup.
  - If coverage 2 should get all the group markup plus part of the XCore
    markup: give up with no markups, and set the giveup markup to the group
    markup plus the extra.
- Giveup config is matched on connector, account, symbol, provider, book and
  more. Fields support negation and wildcards, e.g. symbol `!XAUUSD, *`. Book
  values look like `a_only`. `VALUE` is a comma-separated config string with
  the coverage login, the giveup markup and other settings.
- Example row: connector `mt4_uk`, account (name), symbol `!XAUUSD, *`,
  provider `saxo`, book `a_only`, value `[login, giveup markup, ...]`.
- **Josh's mimic:** read the giveup table row by row, turn each field into a
  regular-expression `WHERE` clause, query the XCore order table, and append
  the coverage login. Done as a recursive query that reproduces XCore's rule
  ordering. This rebuilds the coverage trades with full detail.

### Config history

- At work Josh read the XCore logs directly. An XCore audit-log table is new to
  him; the project simulates one (`CONFIG_AUDIT_LOG`).
- Josh's method, and his resume item: capture config changes, then for any
  order, rebuild the exact settings at order time. With an audit log, treat
  it as a stack and "pop" back to the setting just before the order time,
  joining on order time.

## Business context (from the resume)

- Equiti Capital, 2014-2024. FX, metals and CFDs; retail and B2B; nested
  entities (e.g. UK, offshore); partner rebates; principal (B-book) and
  straight-through (A-book) models; later a prime-broker settlement model.
- Reporting needs: true per-trade P&L including rebates, net revenue as the
  primary metric, markout analysis, reconciliation across MT4, XCore and
  providers.
