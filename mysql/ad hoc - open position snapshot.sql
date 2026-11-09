-- EXPLAIN ANALYZE 
/*
select *
from (
	select ticket, login, symbol, cmd, open_time, open_price, cast(substring_index(`comment`,' ',-1) as unsigned) hedge_ticket
	from mt4.mt4_trades
	where left(`comment`,14) = 'close by hedge'
) a
join mt4.mt4_trades b
on a.hedge_ticket = b.ticket;*/

set @snap_time = (select close_time from reference.eod_time where trade_date = '2026-11-03');
    
WITH
hedge as (
	select ticket, login, symbol, cmd, open_time, open_price, cast(substring_index(`comment`,' ',-1) as unsigned) hedge_ticket
	from mt4.mt4_trades
	where left(`comment`,14) = 'close by hedge'
),
closed as (
	select ticket, login, symbol, cmd, VOLUME, open_time, close_time, commission, `swaps`, profit, `comment` 
    from mt4.mt4_trades
    where cmd in (0,1)
    and close_time <> '1970-01-01 00:00:00'
    and ticket not in (select ticket from hedge)
),
floating as (
	select ticket, login, symbol, cmd, VOLUME, open_time, close_time, commission, `swaps`, profit, `comment` 
    from mt4.mt4_trades
    where close_time = '1970-01-01 00:00:00'
    and cmd in (0,1)
)
select symbol, cmd, sum(volume)
from (
	select hedge.ticket, hedge.login, hedge.symbol, hedge.cmd, closed.volume,
		   hedge.open_time, '1970-01-01 00:00:00' as close_time,
		   closed.commission/2 as commission, closed.`swaps`/2 as `swaps`, null as profit, null as `comment`
	from hedge
	join closed
	on hedge.hedge_ticket = closed.ticket
    where hedge.open_time < @snap_time
    and closed.close_time >= @snap_time
	union all
	select *
	from closed
	where open_time < @snap_time
    and close_time >= @snap_time
	union all
	select *
	from floating
	where open_time < @snap_time
) pos
where login = 100001
group by 1,2;