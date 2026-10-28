select conn.name as connector, acct.name as `account`,
	   pool.PROVIDER_ID, pool.xcore_symbol,
       prof.MARKUP_BID, prof.MARKUP_ASK, prof.B_BOOK,
       sym.DIGITS
from xcore.xcore_connectors conn
left join xcore.xcore_connector_accounts acct
on conn.CONNECTOR_ID = acct.CONNECTOR_ID
left join xcore.xcore_liquidity_pool_providers pool
on acct.POOL_ID = pool.POOL_ID
left join xcore.xcore_profile_symbols prof
on acct.PROFILE_ID = prof.PROFILE_ID
and pool.xcore_symbol = prof.XCORE_SYMBOL
left join REFERENCE.XCORE_SYMBOL_REFERENCE sym
on pool.XCORE_SYMBOL = sym.XCORE_SYMBOL
where conn.NAME <> 'trade/mt4';