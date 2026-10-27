SELECT mt4.*, 
	   sym.XCORE_SYMBOL, sym.DIGITS, sym.POINT, sym.CONTRACTS_PER_LOT, sym.SCALING_MULTIPLIER,
       prof.MARKUP_BID, prof.MARKUP_ASK, prof.B_BOOK,
       pool.PROVIDER_ID
FROM reference.connector_account_logins mt4
left join reference.symbol_reference sym
on mt4.symbol = sym.mt4_symbol
left join xcore.xcore_liquidity_pool_providers pool
on mt4.pool_id = pool.pool_id
and sym.XCORE_SYMBOL = pool.XCORE_SYMBOL
left join xcore.xcore_profile_symbols prof
on mt4.profile_id = prof.profile_id
and sym.XCORE_SYMBOL = prof.XCORE_SYMBOL;