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
- Security groups as Josh defined them (`MT4_SECURITIES`), splitting FX by
  symbol suffix so groups can be set per suffix:

  | Index | Name | Description | Symbols (`MT4_SYMBOLS.TYPE`) |
  |---|---|---|---|
  | 1 | PLAIN | | 13 plain FX pairs (`EURUSD`) |
  | 2 | .retail | RETAIL FX | 13 `.retail` pairs |
  | 3 | .b2b | B2B FX | 13 `.b2b` pairs |
  | 4 | METAL | XAUUSD, XAGUSD | 2 metals |
  | 5 | CFD | USOIL, UKOIL, NAS100, SP500 | 4 CFDs |

- Each client group gets exactly one FX security group, plus metals and
  CFDs (`MT4_GROUP_SECURITIES`), so it can only trade its own FX suffix:
  Retail groups and White Label trade `.retail`, B2B and Coverage trade
  `.b2b`, House trades the plain symbols. Rebate has no rows at all, because
  rebate logins don't trade.
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
  - Commission is a field on the trade's `MT4_TRADES` row; there is no
    separate commission record.
  - Josh first remembered commission as charged **at open only**, for both
    sides (2x the per-side amount). On 2026-10-27 he said he doesn't
    actually remember how commission and agent commission were handled. The
    open-only rule also conflicts with close by hedge.
  - So the simulation charges the **open side at open and the close side at
    close**. `COMMISSION` and `COMMISSION_AGENT` are updated at closing time
    to capture both sides. This makes adding up commission for close-by-hedge
    pairs come out right.
  - Partial close pro-rates commission between the tickets. See "MT4 trade
    behaviour: direct clients" below.
  - Conversion: `MT4_TRADES.CONV_RATE1` is the rate from the symbol's base
    currency to the deposit currency. Josh derives the quote-to-deposit rate
    from it and the symbol price. (At work he also used an end-of-day query
    of MT4 prices; the simulation uses `CONV_RATE1` instead.)
    Standard MT4 may define `CONV_RATE1`/`CONV_RATE2` as profit (quote)
    currency to deposit, with `MARGIN_RATE` for the base currency. Josh can't
    check this. The PrimeXM bridge may have overridden it, so the simulation
    keeps his definition: `CONV_RATE1` = base to deposit.
  - Two rates, both needed: `CONV_RATE1` at open and `CONV_RATE2` at close.
    Under the open-then-close rule, the open side of commission uses
    `CONV_RATE1`. The close side is assumed to use `CONV_RATE2`; Josh hasn't
    confirmed this.
  - Worked example, `COMM_BASE` 10, 1 lot EURUSD at about 1.10, USD account:
    notional 100,000 EUR = 110,000 USD, so $11 per side. `COMMISSION` is
    -11.00 at open and about -22.00 after close.
  - Because commission is linear in notional, `COMM_BASE` USD per 100,000 USD
    is the same as `COMM_BASE` deposit currency per 100,000 of deposit
    currency. So, per side: `COMM_BASE` x lots x `CONTRACT_SIZE` x
    `CONV_RATE1` / 100,000, in deposit currency, with no extra rate table.
  - `LOT_MIN` 0.01 and `LOT_MAX` 100, in lots: in config, 1 means 1 lot.
    Min 0.01 lets FX clients trade 1,000 units at a time. CFDs (security
    group 5) trade in whole lots, min and step 1, for every group except
    House and Rebate.
  - Trades are different: `MT4_TRADES.VOLUME` is an integer in hundredths of
    a lot (0.01 lot = 1, 1 lot = 100). Josh's ELT gets units with
    `VOLUME` / 100 x `CONTRACT_SIZE`.
- MT4 quirks to keep: one row per ticket updated in place (`MODIFY_TIME`);
  open trades have `CLOSE_TIME = 1970-01-01`; `VOLUME` in hundredths of a lot;
  `CMD` 6 = balance operation with amount in `PROFIT`; partial close creates a
  new ticket (`from #` / `to #` comments). Server time is GMT (see Time).

## XCore (PrimeXM bridge)

Josh's setup order, which is also the dependency order of the tables:

1. **Providers** (PrimeXM: makers): name, FIX connection specs.
2. **Provider symbol -> XCore symbol mapping.** Many to one: Bank A
   `EUR/USD` and Bank B `EURUSD.ecn` both map to XCore `EURUSD`. Josh chose
   not to model this table; providers are treated as quoting XCore symbols
   directly.
3. **Liquidity pools**: the set of providers for each XCore symbol.
4. **Profiles**: markup, commission, etc.
5. **Connectors** (PrimeXM: takers): the connection to a client system.
6. **Connector account** (child of connector): handles trading.
7. **Connector stream** (child of connector): handles pricing.
8. Liquidity pool and liquidity profile are applied to the account and the
   stream, which customises pricing, trading, profit and markup.

How this project models 5-8, as Josh set it up:

- Connectors (`XCORE_CONNECTORS`, name and description): `trade/mt4` for the
  MT4 server, plus one giveup connector per B2B coverage login:
  `trade/uk_cov_100`, `trade/uk_cov_200`, `trade/nz_cov_300`,
  `trade/nz_cov_400` (giveups to MT4 logins 100-400).
- Connector accounts (`XCORE_CONNECTOR_ACCOUNTS`): a connector can have
  several. `trade/mt4` has one per business: Retail, B2B, WL, Toxic, House,
  each with the profile of the same name. Each giveup connector has one
  account (`uk_cov_100` etc.) on the B2B profile. All accounts start on pool
  Bank_FX.
- Which MT4 trades go to which account: in reality a bridge between MT4 and
  XCore does this mapping. Josh doesn't want to build one, so each connector
  account carries match fields instead: `GROUP`, `LOGIN` and `LEAD_SOURCE`
  (comma-separated lists, `*` = anything, `NULL` = nothing). A trade goes to
  the account whose three fields all match its MT4 login. This lets MT4
  client clusters be split across accounts.

  | Account (trade/mt4) | Matches |
  |---|---|
  | Retail | groups RetailUSD/EUR/JPY/GBP |
  | B2B | group B2B |
  | WL | group White Label, lead source WL |
  | Toxic | nothing for now (all NULL) |
  | House | group House, logins 20 and 50 (the trading House logins) |

  The giveup connectors' accounts match by login: `uk_cov_100` = login 100,
  and so on.
- Who trades through what:
  - Retail, B2B, House and WL clients place trades in the MT4 client
    terminal. Those trades reach XCore through the MT4 bridge on connector
    `trade/mt4` (connector 1).
  - The giveup connectors (`trade/uk_cov_100` etc.) are B2B clients whose
    own trading platform sends FIX straight to XCore, without the broker's
    MT4. The broker gives up (drop-copies) their trades to a coverage MT4
    login (100-400) to keep an eye on them, because MT4 doubles as a hacked
    back office.
  - Coverage logins (100-400, 100000) never trade directly; they only
    receive giveup copies.
- The simulated bridge is Josh's stored procedure
  `reference.connector_account_login()` (`mysql/stored procedure - connector
  account login.sql`). It builds every MT4 login and symbol with group
  settings, loops over the `trade/mt4` connector accounts only (connector 1)
  with a cursor, turns each account's three patterns into regexes
  (`reference.pattern_pos_re` / `pattern_neg_re`, the same rules as
  giveups: `*`, `!`, comma lists) and writes the matches to
  `reference.connector_account_logins`, one row per account, login and
  symbol. Current run: 522 logins mapped, none twice; unmapped by design:
  the 5 coverage logins. Checked against the accounts: every trading login matches
  exactly one trade/mt4 account. Unmatched, as expected: House 10/30/40
  (giveup targets), Coverage logins, Rebate logins. An account's pool can change over time, through
  `fxgen/pools.py assign`, which logs it. Open: the Toxic account says
  Bank_FX, but the Toxic profile's symbols all point to Toxic_FX; which one
  wins is not settled yet.
- No connector streams: Josh dropped them. A separate stream could show a
  client BankA's price when the account can't actually trade BankA's
  liquidity. That is predatory and probably not allowed after MiFID. Without
  streams, pricing and trading come from the same pool.
- No XCore -> MT4 symbol mapping table either (Josh dropped it). XCore
  `EUR/USD` maps to MT4 `EURUSD`, `EURUSD.retail` and `EURUSD.b2b` by rule:
  remove the slash for FX, use `CCY1` for CFDs.

- Providers, as Josh defined them (`XCORE_PROVIDERS`, cut down to name, FIX
  comp IDs and enable): 1 BankA, 2 BankAToxic, 3 BankB, 4 BankBToxic. Each
  bank has a normal and a "Toxic" provider; what Toxic means is still to be
  written down. The FIX comp IDs are invented: sender = the bridge's side,
  target = the bank, one session per provider.
- Liquidity pools, as Josh defined them: 1 Bank_FX (FX and metals from
  providers 1,3 = BankA, BankB) and 2 Toxic_FX (FX and metals from providers
  2,4 = the two Toxic providers). Both pools also carry the 4 CFDs, from
  provider 1 = BankA only, so each profile takes every symbol from one pool.
  (An earlier separate CFD pool, Bank_A_CFD, was dropped.)
  `XCORE_LIQUIDITY_POOL_PROVIDERS.PROVIDER_ID` is a CSV of provider IDs per
  pool and symbol. Josh doesn't remember whether XCore stored it that way,
  but it's fine for this project.
- Pool changes in the simulation: providers are never edited, but existing
  providers are dropped from or added to the FX pools. Always through
  `fxgen/pools.py`, so every change is logged. Josh will give the rules for a
  random daily mode (which providers may join or leave which pool).
- Profiles, as Josh defined them: 1 Retail, 2 B2B, 3 WL, 4 Toxic, 5 House.
  Per profile and symbol (`XCORE_PROFILE_SYMBOLS`): the liquidity pool used
  and the XCore markup. Retail, B2B, WL and House use Bank_FX for every
  symbol; Toxic uses Toxic_FX. House has zero markup everywhere. Each
  profile symbol also carries the B-book flag (see Trade tables).
  - A profile symbol is the symbol-level config of one profile. To change a
    client's markup, either move the client (its connector account) to a
    different profile, or change the details of its profile's symbols.
  - A real company would usually have one profile per client company rather
    than sharing one profile across many companies. Here B2B is shared by the
    B2B account and the four giveup accounts.
  - In the simulation, accounts never move between profiles: the markup is
    steady. What does move is an account's pool, because a bank can flag a
    client as toxic, and the account is then moved to the toxic pool
    (`fxgen/pools.py assign`).
  - Markup is in price units, added to the price: `MARKUP_BID` <= 0 (e.g.
    -0.00002 on EUR/USD = 2 points off the bid), `MARKUP_ASK` >= 0. Josh's
    rows are all symmetric (bid = -ask). The signs are enforced by CHECK
    constraints.
  - Both the pool and the markup can change over time. Changes go through
    `fxgen/profiles.py`: `set` for a chosen change, `random` for the daily
    churn. Random markup moves up or down by 1-2 points of the symbol and
    stops at zero; it never flips a sign. House is never changed.
  - Connector accounts carry a pool too, so the pool is set in two places.
    See the open Toxic question under connector accounts.
- **XCore symbol -> MT4 symbol** is one to many: XCore `EUR/USD` maps to MT4
  `EURUSD`, `EURUSD.retail` and `EURUSD.b2b`.
- XCore symbols (`XCORE_SYMBOLS`: `SYMBOL`, `TYPE`, `CCY1`, `CCY2`) come from
  a reference table Josh built at work. It mapped every MT4 symbol to one
  XCore symbol so that symbols aggregated correctly. PrimeXM's own symbol
  schema isn't public. 19 symbols:
  - FX pairs in slash form (`EUR/USD`). Metals count as FX here (`XAU/USD`,
    `XAG/USD`), unlike MT4, where they're security group METAL.
  - CFDs by market name: `WTI`, `Brent`, `Nasdaq`, `SP500`. For these, `CCY1`
    holds the underlying (`USOIL`, `UKOIL`, `NAS100`, `SP500`), which is also
    the MT4 symbol name.
  - Josh confirmed both splits are true to the business: asset-class reports
    group metals differently in MT4 and XCore, and mapping between the systems
    needs the slash removed for FX and `CCY1` for CFDs.
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
- `DEAL`: the provider's execution. Not simulated for now; see "Deals and
  rounding gaps" below.
- Josh's reporting join: `ORDER LEFT JOIN LEG LEFT JOIN DEAL`.
- Where A/B-book is decided in config: Josh set it on the profile symbol,
  `XCORE_PROFILE_SYMBOLS.B_BOOK` (1 = B-book, 0 = A-book). Retail and WL
  are B-booked on every symbol; B2B, Toxic and House are A-booked. The
  `b_book` result on `LEG` follows from it, and giveup rule 1 (book
  `b_only`) copies the B-booked trades to login 10.

### Execution tables (Josh's notes, for the execution simulation)

Built in `mysql/xcore_trades.sql` as `XCORE_ORDER_MT4`, `XCORE_ORDER` and
`XCORE_LEG`. The table below keeps Josh's field descriptions; Josh will add
more as the simulation is built and tested. "Contracts" means after
converting from lots and applying the scaling multiplier (`TICK_VALUE` /
`TICK_SIZE`). Times are epoch milliseconds.

**XCore order MT4** (`XCORE_ORDER_MT4`)

Primary key: clordid, the working ticket number. It auto-increments, giving
one row per MT4 request to open or close a ticket, rejected attempts
included. MT4 passes it to XCore as `ORDER.subid2`. Ticket and order ID are
each indexed. Columns stay in Josh's order, with login and clordid added at
the front.

Order ID is NULL until XCore creates the order.

ORDER_ID was added to the real table later. Before it existed, the join to
`ORDER` matched login, symbol and connector, plus order open_milli within a
minute of order MT4 open_milli. Josh won't recreate that: it's needlessly
complicated. Here the join is ORDER_ID alone, and ORDER_ID is indexed for it.

| Field | Meaning |
|---|---|
| login | MT4 login |
| clordid | working ticket number; auto-increment primary key |
| ticket | MT4 ticket number |
| close | 0 or 1 |
| symbol | MT4 symbol |
| side | buy/sell |
| amount | requested contracts after converting from lot and applying the scaling multiplier |
| price | requested price (raw price with markup bid/ask and group markup) |
| fillsize | executed amount in contracts after converting from lot and applying the scaling multiplier |
| fillprice | all-in executed price with all markups |
| orderID | XCore order ID |
| open_milli | epoch time x 1000: ticket request time; for MT4 trades, the earliest timestamp |
| close_milli | epoch time x 1000: ticket fill time; for MT4 trades, the last timestamp |

**XCore order** (`XCORE_ORDER`)

| Field | Meaning |
|---|---|
| orderID | auto increment from 1 |
| symbol | XCore symbol |
| side | buy/sell |
| connector | connector name, e.g. trade/mt4 |
| account | connector account name |
| subid1 | MT4 login or null |
| subid2 | order MT4 clordid or null: how MT4 passes clordid to XCore |
| subid3 | MT4 group or null |
| subid4 | MT4 lead source or null |
| amount | requested trade size (same as order MT4 amount) |
| price | requested trade price: raw price with markup bid or ask. XCore doesn't know anything about group markups |
| fillsize | executed size (passed back to order MT4) |
| fillprice | executed price + markup bid/ask (again, doesn't know anything about group markups) |
| open_milli | epoch time x 1000: order request time, a few milliseconds after order MT4 open_milli |
| close_milli | epoch time x 1000: order complete time, later than order open and leg close |

**XCore leg** (`XCORE_LEG`)

| Field | Meaning |
|---|---|
| orderID | matches the parent orderID |
| legID | starts at 0 for every new orderID; increments as more legs are used |
| b_book | 0 or 1, based on config |
| symbol | XCore symbol |
| side | buy/sell |
| amount | requested leg amount, smaller than the order trade size |
| price | requested price (the LP's quoted price) |
| fillsize | LP fill size |
| fillprice1 | LP executed price, raw |
| fillprice2 | LP executed price with XCore markups added |
| lp | provider ID: whose price the leg executed on. Still a real LP even if B-booked |
| markup_bid | XCore markup on the bid applied to this leg (from the profile symbol at the time) |
| markup_ask | XCore markup on the ask applied to this leg |
| open_milli | epoch time x 1000: leg request time, a few milliseconds after order open_milli |
| close_milli | epoch time x 1000: leg complete time, the earliest of the closing timestamps |

Timestamp order for one MT4 trade: order MT4 open < order open < leg open <
leg close < order close <= order MT4 close.

`close_milli` is never empty: a rejected order still gets the time of the
rejection. A rejection shows as fill size and fill price 0 (on a leg, both
fill prices), so the fill columns are never empty either.

Fill rules (Josh):

- When an order is done, the sum of its legs' fill sizes equals the order
  fill size, which normally equals the order MT4 fill size (exception
  below).
- Never send more legs than needed to reach the requested size.
- Rejections and failed trades happen. Fill size can be less than the
  request, never more.
- Price slippage happens: about 95% in the bad direction (buy fills higher,
  sell fills lower than the leg's quoted price), about 5% in the good one.
- Partial fills below the MT4 lot step: with correct config, XCore doesn't
  allow partial fills that aren't a multiple of the MT4 lot step. With bad
  config it does, and MT4 floors the fill to a size it can hold (the group's
  `LOT_STEP`, in contracts). The remainder was filled at the provider but
  isn't on any MT4 ticket, so the broker has unknowingly taken on a hidden
  position. The simulation assumes bad config but keeps this rare. It shows
  up as order fill size > order MT4 fill size.

Execution simulation, `fxgen/orders.py` (first version, for Josh to check).
It starts from Josh's tradeable-login query over the bridge output. Choices
made there, to confirm or correct:

- The pool comes from the connector account (Josh's query joins on
  `mt4.pool_id`); the profile symbol supplies markup and B-book.
- The pool's provider CSV is the list of possible providers. Each provider
  quotes 4 levels of 10 lots, each 1 point worse. An order sweeps the levels
  best-first across providers; each leg hits one provider at one level, so
  leg prices get worse as the sweep goes deeper.
- A rejected leg is retried on the next level once its rejection comes back;
  sweep legs go out a few ms apart.
- B-book legs (Retail, WL) fill in full at the quote: no rejections, no
  slippage, real LP still named.
- A rejected opening order creates no MT4 ticket: order MT4 `TICKET` is 0.
  It still has a CLORDID, so `SUBID2` is set.
- `python -m fxgen.orders sample --date ... --replace` writes one set per
  scenario: normal, sweep, reject then retry, all rejected, partial fill,
  hidden position, good slippage, B-booked metal, mini CFD, rejected close
  then retried.
- It then writes one API order per scenario: fill, sweep, partial, all
  rejected, adverse slip. They are spread across the four API accounts, with
  no order MT4 row and NULL subids. Their profile comes from Josh's API
  query, with lot limits from the Coverage group.

Price flow. Each layer only knows its own markup: XCore knows nothing about
MT4 group markups, and providers know nothing about XCore markups (not
simulated, but the leg records it).

| Table | Request price | Fill price |
|---|---|---|
| Leg | `price` = the LP's quote | `fillprice1` = LP executed, raw (slippage lands here); `fillprice2` = `fillprice1` + XCore markup |
| Order | raw price + XCore markup | executed price + XCore markup (from the legs' `fillprice2`) |
| Order MT4 | raw price + XCore markup + MT4 group markup | all-in: order fill price + MT4 group markup |

Buys use the ask and the ask markup; sells use the bid and the bid markup.

MT4 group markup (`SPREAD_DIFF`, in points) is split across the life of a
ticket: half on the opening fill and half on the closing fill. If it is odd,
the open gets the extra point: open = ceil(`SPREAD_DIFF` / 2), close =
floor(`SPREAD_DIFF` / 2). Each half goes against the client on that fill
(added on a buy, subtracted on a sell), x `MT4_SYMBOLS.POINT`.

| `SPREAD_DIFF` | Open | Close |
|---|---|---|
| 2 (Retail FX, WL metals) | 1 | 1 |
| 10 (WL FX) | 5 | 5 |
| 3 (example) | 2 | 1 |

Price precision and rounding:

| Table | Precision |
|---|---|
| Leg (`price`, `fillprice1`, `fillprice2`) | the symbol's `DIGITS` |
| Order `fillprice` | size-weighted average of the legs' `fillprice2`, unrounded (can have any number of decimals) |
| Order MT4 `fillprice` | back to `DIGITS`, rounded in the broker's favour: buys round up (ceiling), sells round down (floor) |

E.g. on a 5-digit symbol, a buy averaging 1.000011 becomes 1.00002 in MT4,
and a sell averaging 1.000099 becomes 1.00009. The gap between the order
and the MT4 fill price is a small, always broker-favourable difference that
shows up in reconciliation. Josh isn't sure this rounding was legal.

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
- Giveup rules in this project (`XCORE_GIVEUPS`), as Josh defined them.
  Match fields are connector, account, symbol, MT4 group, login, lead source
  and book; `TARGET` is the coverage login. `REVERSE` = 1 flips the copy's
  side. `WITH_MARKUP` says whether the copy is priced with the XCore markup
  (1) or without it (0). All values are kept verbatim as XCore holds them.
  Book values (`b_only`, `any`, `*`) are XCore-accurate and must not be
  translated. `GIVEUP_ID` is the rule order.

  | ID | Connector | Matches | Book | Target | Reverse | With markup |
  |---|---|---|---|---|---|---|
  | 1 | trade/mt4 | everything | `b_only` | 10 NZ B Book Giveup | 1 | 0 |
  | 2 | trade/mt4 | lead source `NZ_*` | `any` | 30 NZ All Client Giveup | 0 | 0 |
  | 3 | trade/mt4 | lead source `UK_*, NZ_*` | `any` | 40 UK All Client Giveup | 0 | 0 |
  | 4 | trade/mt4 | group White Label | `any` | 100000 White Label Coverage | 0 | 0 |
  | 5-8 | each giveup connector | its own account | `any` | 100, 200, 300, 400 | 0 | 1 |

  Login 40 is labelled UK but also takes NZ clients.
- **Josh's mimic:** read the giveup table row by row, turn each field into a
  regular-expression `WHERE` clause, query the XCore order table, and append
  the coverage login. Done as a recursive query that reproduces XCore's rule
  ordering. This rebuilds the coverage trades with full detail.
- Built as `reporting.giveup()` (`mysql/stored procedure - giveup.sql`).
  - A cursor reads the rules in `GIVEUP_ID` order, turns each one into regex
    conditions and appends its matches to `reporting.giveup_trades`.
  - Josh's outputs: `GIVEUP_LOGIN` is the rule's `TARGET`.
  - `GIVEUP_PRICE` is the order fill price (the order's size-weighted average,
    with XCore markup) when `WITH_MARKUP` = 1. It is the leg's `FILLPRICE1`
    when `WITH_MARKUP` = 0.
  - The price is then rounded to the symbol's digits in the broker's favour,
    the same possibly illegal floor/ceiling rule MT4 uses: buys round up,
    sells round down.
    - Only the order average needs rounding; a leg price is already on the
      digits.
    - Every leg of a swept order is copied at the same rounded average.
  - `DIGITS` comes from `reference.xcore_symbol_reference`.
  - The rows it matches come from Josh's order / leg / order MT4 reporting
    query, with the matched fields added.
  - Every matching rule makes a copy, so an NZ B-book retail trade goes to 10,
    30 and 40.
  - Choices made, not confirmed by Josh:
    - Grain is one row per filled leg; rejected legs are not copied.
    - `b_only` needs leg `B_BOOK` = 1, `a_only` needs 0, and `any` or `*`
      matches both.
    - A missing subid counts as '' so that `*` still matches it.

### API trades (Josh, 2026-10-27)

- API clients trade on the non-MT4 connectors, sending FIX straight to XCore.
  Josh's query for their trading profile is the API version of the bridge.
  It reads connector → connector account → pool providers per XCore symbol
  → profile markup and B-book flag, for `conn.NAME <> 'trade/mt4'`.
- In this project these are the four coverage connectors: `trade/uk_cov_100`,
  `uk_cov_200`, `nz_cov_300` and `nz_cov_400`.
  - Each has one account with the same name.
  - Every one of those accounts is on pool 1 Bank_FX and profile 2 B2B.
  - They are A-booked on all 19 XCore symbols.
- An API trade has **no order MT4 row**.
- Its legs are exactly the same as an MT4 client's.
- Its order is the same as an MT4 client's, except that SUBID1-4 are all NULL.
- An API trade **gets a login only at giveup**: giveup rules 5-8 match the
  connector and account, and copy the trade, with markup, to coverage login
  100, 200, 300 or 400.
- **Size limits:** XCore has its own min, max and step settings per symbol,
  independent of MT4's. In practice the two systems should be set the same.
  Hidden exposure comes from getting them wrong: a fill size that one system
  rounds and the other doesn't. The simulation reuses the MT4 limits for API
  trades, taken from the Coverage group, where the giveup logins live.
  - FX and metals: min 0.01 lots, max 100, step 0.01.
  - CFD: min 1, max 100, step 1.
  - These match B2B. Lots are converted to XCore units the same way as for
    MT4 trades.
- **No open or close in XCore:** an order is just an order. An API client's
  trades are plain buys and sells. How giveups land on MT4 tickets comes
  later.
- **Execution:** API clients can be rejected, partly filled and slipped,
  just like MT4 clients.
  - Fill size 0 means rejected.
  - XCore has retry settings, but they aren't simulated: an API order that
    is rejected or partly filled stays that way.
- **Volume:** the API clients are B2B, usually brokers themselves, and they
  trade a lot. API (B2B) volume should be 40-50% of total daily volume; the
  rest comes from the MT4 direct accounts.

### Deals and rounding gaps (Josh, 2026-10-27)

**Deals.** The XCore flow is order > leg > deal:

| Table | Is | Key |
|---|---|---|
| Order | the client's request | order ID |
| Leg | the request to an LP | order ID, leg ID |
| Deal | the LP's execution | order ID, leg ID, deal ID |

- An LP can split a leg into many deals, just as XCore splits an order into
  legs.
- Deal ID counts up within each leg.
- The true primary key of the trade flow is order ID, leg ID and deal ID.
- So leg `fillprice1` and `fillprice2` can be volume-weighted averages of the
  deals, with more digits than the symbol has. They then face the same XCore
  to MT4 rounding as the order fill price.
- Not simulated for now: every simulated leg fills as one deal at a price on
  the symbol's digits.

**Rounding gaps.**
- Rounding "in the broker's favour" really means against the client, because
  the clients are on MT4.
- For a regulated STP broker, rounding that left a trade with negative
  revenue could be a problem.
- Rounding becomes a discrepancy once the broker also uses MT4 as its
  internal book of truth:
  - **LP reconciliation:** say a giveup sends every A-book trade against
    LP 1 to account X. Comparing X with LP 1's statement shows a difference
    from the rounding.
  - **Reverse giveups:** these are more of a problem. The house risk account
    usually gets a reverse giveup: the client buys, so the risk account
    sells. A volume-weighted price already has more digits than the symbol.
    On top of that, the copy's side is flipped, so the rounding goes the
    wrong way. The risk account isn't a client, so rounding against it is
    rounding against the broker.
    - Example: the GBP/USD sweep averages 1.2702933.
    - A client buy rounds up to 1.27030.
    - The risk account's reverse sell rounds down to 1.27029.
    - So the client's trade and the risk account's copy don't net to zero.
- **Reverse giveups** are configured by `XCORE_GIVEUPS.REVERSE`: 1 flips
  the copy's side, 0 keeps it.
  - Rule 1 (B-book to login 10, the NZ B-book risk account) is the reverse
    one.
  - `reporting.giveup()` writes the copy's side as `GIVEUP_SIDE`.
  - It rounds `GIVEUP_PRICE` by that side, like any MT4 login, with no
    special rule for the risk account. Josh deals with the resulting gap in
    reporting.

### MT4 trades (Josh, 2026-10-27)

`mt4.MT4_TRADES` (`mysql/mt4_trades.sql`) is the MT4 MySQL export table
`MT4_TRADES`, the Manager API's `TradeRecord`, cut down to Josh's fields.

- **Cash rows:** MT4 keeps deposits and withdrawals in the trade table, as
  `CMD` 6 balance and 7 credit.
- **CMD codes:** 0 buy, 1 sell, 2 buy limit, 3 sell limit, 4 buy stop,
  5 sell stop, 6 balance, 7 credit.
- **Left out:** SL, TP, expiration, taxes, internal ID, margin rate, magic,
  timestamp, reason, the gateway (GW_) fields and modify time.
- **Number types:** prices, rates and money are DOUBLE, as in the real
  export.

| Field | Meaning |
|---|---|
| SERVER | trade/mt4, consistent with the other MT4 tables |
| TICKET | links to order MT4 `TICKET` |
| LOGIN | links to `MT4_USERS` |
| SYMBOL | MT4 symbol, e.g. EURUSD.b2b |
| DIGITS | price rounding |
| CMD | 0 buy, 1 sell; also 6 balance and 7 credit for cash rows |
| VOLUME | whole number, 100 = 1 lot |
| OPEN_TIME | from the opening order MT4 row, format YYYY-MM-DD hh:mm:ss |
| OPEN_PRICE | locked in on open |
| CLOSE_TIME | from the closing row; 1970-01-01 00:00:00 while open |
| CLOSE_PRICE | updates until closed |
| CONV_RATE1, CONV_RATE2 | base currency to deposit currency (Josh's definition), at open and at close (see "Commission" above) |
| COMMISSION | open side at open; close side added at close |
| COMMISSION_AGENT | the rebate logins (`AGENT_ACCOUNT`) earn this |
| SWAPS | see below |
| PROFIT | see below |
| COMMENT | "a whole can of worms" that Josh will explain soon |

**Swaps.**
- The swap plugin sets a swap price delta, which is used to calculate a
  dollar amount.
- Each day the swap amount = the previous day's swap amount + the new day's
  calculation.
- The swap total locks in when the trade closes.

**Profit.**
- Profit changes with the close price, which floats with the market until
  the trade is truly closed.
- Once the trade is closed, profit is locked in.

**Money is in deposit currency.**
- P/L is always in the account's deposit currency, never the quote currency.
  The same goes for commission, agent commission and swaps.
- Amounts are rounded to the deposit currency. The simulation assumes 0
  decimals for JPY and 2 for USD, GBP and EUR.

### MT4 trade behaviour: direct clients (Josh, 2026-10-27, first pass)

Josh is explaining this over several iterations. It is the spec for the
program that will fill `MT4_TRADES`.

**What a direct client (trading on MT4) can do.**
- **Open trades.** The client can leave a comment, but it is usually blank.
  MT4 system comments override any client or plugin comment.
- **Close** any trade they currently have open.
- **Leave trades open.** A client can hold a buy EURUSD and a sell EURUSD at
  the same time. They can't cash out until they close, but the system allows
  it.
- **Close by hedge.** With open trades in the same symbol on opposite sides,
  the client can select a list of them and close them against each other.

**Close by hedge.**
1. Make two lists, one of buys and one of sells, each sorted oldest first.
   Josh doesn't know MT4's real order, but oldest first does no harm.
2. Take the top of each list.
   - **Main trade (ticket 1):** always the older of the two, whatever its
     size. It stays as the closed trade.
   - **Closing trade (ticket 2):** the newer one, set to volume 0.
   - This way ticket 1 never closes before it opened.
3. If the volumes differ, the bigger ticket is first **partially closed**.
   The bigger one may be either ticket 1 or ticket 2. It is split into two
   tickets:
   - The original ticket ID is reduced to the smaller ticket's volume.
   - A **child ticket** is opened for the remaining volume:
     - Open time, and presumably symbol, side and open price, are the
       parent's.
     - Close time is 1970-01-01 00:00:00.
     - Comment is `from: [ticket 1]`. It always points to the ticket that
       keeps volume, which is ticket 1, whichever ticket was the parent. It
       says the child came from closing that ticket with non-zero
       attributes.
   - The parent's commission, agent commission and swaps are split by
     volume:
     - The reduced ticket's share is rounded to the deposit currency.
     - The child gets the original amount minus that rounded share, so the
       two always add back to the original.
   - Partial close works the same way however it is caused: by close by
     hedge or by another method.
4. Ticket 1 (now the same size as ticket 2):
   - Close time = ticket 2's open time.
   - Close price = ticket 2's open price.
   - Add ticket 2's commission, agent commission and swaps to ticket 1.
   - Calculate profit and lock it in, using `CONV_RATE2` at that close time.
   - The comment says nothing, even if ticket 1 was reduced by a partial
     close.
5. Ticket 2:
   - Volume = 0.
   - Commission, agent commission and swaps = 0, now that they have moved to
     ticket 1.
   - Close price = its open price, so profit is 0.
   - Close time = when the close by hedge was requested.
   - Comment = `close by hedge: [ticket 1]`.
6. Keep pairing down the lists until one runs out. The lists can change as
   it goes: a remainder ticket from step 3 takes the parent's place.
   Partial closes will be covered later.

**XCore doesn't know about close by hedge.** Nothing is sent to XCore, so
MT4 and XCore volumes diverge. That's why Josh had to brute-force trade
matching once the volumes on the two systems differed.

### Config history

### Config history

- At work Josh read the XCore logs directly. An XCore audit-log table is new to
  him; the project simulates one (`XCORE_CONFIG_AUDIT_LOG`): auto-increment
  `LOG_ID`, `LOG_TIME` (GMT, milliseconds) and a fixed-format `MESSAGE`, e.g.
  `Liquidity pool 1 Bank_FX, symbol EUR/USD: removed provider 3 BankB.
  Providers 1,3 -> 1.` One row per pool and symbol changed, written in the
  same transaction as the change by `fxgen/pools.py` or `fxgen/profiles.py`
  (e.g. `Profile 1 Retail, symbol EUR/USD: markup bid -0.00002 -> -0.00003,
  ask +0.00002 -> +0.00003.`, `Profile 4 Toxic, symbol XAU/USD: pool 2
  Toxic_FX -> 1 Bank_FX.`, `Connector trade/mt4, account 4 Toxic: pool 1
  Bank_FX -> 2 Toxic_FX.`). Each message carries
  the old and new value, so the setting before the first change can be
  rebuilt too. `LOG_TIME` never goes backwards, so `LOG_ID` order is time
  order.
- Josh's method, and his resume item: capture config changes, then for any
  order, rebuild the exact settings at order time. With an audit log, treat
  it as a stack and "pop" back to the setting just before the order time,
  joining on order time.

## Time

- **Both MT4 and XCore record times in GMT.** There is no GMT+2/+3 server
  time here.
- End of day (EOD) still follows the New York close, so in GMT it moves
  with US daylight saving: about 21:00 GMT in US summer time, 22:00 GMT in
  US winter time. Josh will provide a reference file of GMT EOD times. The
  trading day, daily records and swap dates should come from that file.
- The exercise starts close to a DST change (US DST ends 2026-11-01), which
  Josh welcomes: the EOD shift will show up early in the data.

## Business context (from the resume)

- Equiti Capital, 2014-2024. FX, metals and CFDs; retail and B2B; nested
  entities (e.g. UK, offshore); partner rebates; principal (B-book) and
  straight-through (A-book) models; later a prime-broker settlement model.
- Reporting needs: true per-trade P&L including rebates, net revenue as the
  primary metric, markout analysis, reconciliation across MT4, XCore and
  providers.
