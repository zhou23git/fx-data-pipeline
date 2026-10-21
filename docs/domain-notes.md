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
  (`SPREAD_DIFF` = MT4 group markup, commission, lot limits), group margins.
- Security groups as Josh defined them: 1 FX, 2 METAL, 3 CFD (USOIL, UKOIL,
  NAS100, SP500).
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
