drop table if exists reference.symbol_reference;

create table reference.symbol_reference
(primary key (MT4_symbol), index(xcore_symbol))
select SYMBOL as MT4_SYMBOL, `DESCRIPTION`, left(symbol,3) as CCY1, right(left(symbol,6),3) as CCY2,
	   case when `TYPE` in (1,2,3) then 'FX' when `TYPE`=4 THEN 'METAL' WHEN `TYPE`=5 THEN 'CFD' ELSE NULL END `INSTRUMENT`, 
       DIGITS, `POINT`, CONTRACT_SIZE AS CONTRACTS_PER_LOT, 
       CASE WHEN TICK_SIZE=TICK_VALUE THEN 1 ELSE TICK_VALUE/TICK_SIZE END AS SCALING_MULTIPLIER,
       concat(left(symbol,3),'/',right(left(symbol,6),3)) AS XCORE_SYMBOL
from mt4.mt4_symbols
where `type` in (1,2,3,4)
union all
select SYMBOL as MT4_SYMBOL, `DESCRIPTION`, b.xcore_symbol as CCY1, a.currency as CCY2,
	   case when `TYPE` in (1,2,3) then 'FX' when `TYPE`=4 THEN 'METAL' WHEN `TYPE`=5 THEN 'CFD' ELSE NULL END `INSTRUMENT`, 
       DIGITS, `POINT`, CONTRACT_SIZE AS CONTRACTS_PER_LOT, 
       CASE WHEN TICK_SIZE=TICK_VALUE THEN 1 ELSE TICK_VALUE/TICK_SIZE END AS SCALING_MULTIPLIER,
       b.xcore_symbol
from mt4.mt4_symbols a
LEFT join reference.cfd_mapping b
on a.symbol = b.mt4_symbol
where `type` in (5);
