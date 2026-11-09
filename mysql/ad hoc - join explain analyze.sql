	EXPLAIN ANALYZE
    select Trade_Date, login, sum(profit) as closed_profit, sum(commission) as closed_commission, sum(`swaps`) as closed_swaps
    from mt4.mt4_trades a
    left join `reference`.eod_time b
    on a.close_time >= b.open_time
    and a.close_time < date_add(b.close_time, interval 1 second)
    where a.close_time <> '1970-01-01 00:00:00'
    group by 1,2;
    
    
	EXPLAIN ANALYZE
    select Trade_Date, login, sum(profit) as closed_profit, sum(commission) as closed_commission, sum(`swaps`) as closed_swaps
    from mt4.mt4_trades a
    left join `reference`.eod_time b
    on a.close_time >= b.open_time
    and a.close_time < b.close_time
    where a.close_time <> '1970-01-01 00:00:00'
    group by 1,2;
    
    
	EXPLAIN ANALYZE
    select Trade_Date, login, sum(profit) as closed_profit, sum(commission) as closed_commission, sum(`swaps`) as closed_swaps
    from mt4.mt4_trades trades
    left join `reference`.eod_time eodTime
    on trades.close_time >= eodTime.open_time
    and trades.close_time < eodTime.close_time
    where trades.close_time <> '1970-01-01 00:00:00'
    and eodTime.TRADE_DATE between (select date(min(close_time)) from mt4.mt4_trades where close_time <> '1970-01-01 00:00:00') and date_add((select date(max(close_time)) from mt4.mt4_trades), interval 1 day)
    group by 1,2;
    

	set @startTime = concat((select date(min(close_time)) from mt4.mt4_trades where close_time <> '1970-01-01 00:00:00'), ' 00:00:00');
    set @endTime = concat((date_add((select date(max(close_time)) from mt4.mt4_trades), interval 2 day)), ' 00:00:00');
    
	EXPLAIN ANALYZE
    select Trade_Date, login, sum(profit) as closed_profit, sum(commission) as closed_commission, sum(`swaps`) as closed_swaps
    from mt4.mt4_trades trades
    left join `reference`.eod_time eodTime
    on trades.close_time >= eodTime.open_time
    and trades.close_time < eodTime.close_time
    and eodTime.close_time between @startTime and @endTime
    where trades.close_time <> '1970-01-01 00:00:00'
    group by 1,2;
    
    
	set @startTime = concat((select date(min(close_time)) from mt4.mt4_trades where close_time <> '1970-01-01 00:00:00'), ' 00:00:00');
    set @endTime = concat((date_add((select date(max(close_time)) from mt4.mt4_trades), interval 2 day)), ' 00:00:00');
    
	EXPLAIN ANALYZE
    select Trade_Date, login, sum(profit) as closed_profit, sum(commission) as closed_commission, sum(`swaps`) as closed_swaps
    from `reference`.eod_time eodTime
    left join mt4.mt4_trades trades
    on trades.close_time between eodTime.OPEN_TIME and eodTime.CLOSE_TIME
    and trades.close_time <> '1970-01-01 00:00:00'
    where eodTime.CLOSE_TIME between @startTime and @endTime
    group by 1,2;
    

EXPLAIN ANALYZE    
select t.trade_date, t.login,
       sum(t.profit), sum(t.commission), sum(t.swaps)
from (
    select a.login, a.profit, a.commission, a.swaps,
           (select b.trade_date
              from reference.eod_time b
             where b.close_time > a.close_time   -- periods ending after this trade
             order by b.close_time               -- earliest-ending first
             limit 1) as trade_date              -- take just that one
    from mt4.mt4_trades a
    where a.close_time > '1970-01-01 00:00:00'
) t
group by 1, 2;


EXPLAIN ANALYZE  
select
    coalesce(
        (select b.trade_date
           from reference.eod_time b
          where b.trade_date = date(a.close_time)
            and a.close_time >= b.open_time
            and a.close_time <  b.close_time),
        (select b.trade_date
           from reference.eod_time b
          where b.trade_date = date(a.close_time) + interval 1 day
            and a.close_time >= b.open_time
            and a.close_time <  b.close_time)
    ) as trade_date,
    a.login,
    sum(a.profit)     as closed_profit,
    sum(a.commission) as closed_commission,
    sum(a.swaps)      as closed_swaps
from mt4.mt4_trades a
where a.close_time > '1970-01-01 00:00:00'
group by 1, 2;