set @startDate = '2026-11-01';
set @endDate = '2026-11-09';
set @startTime = '2026-11-01 00:00:00';
set @endTime = '2026-11-09 00:00:00';


/*   
EXPLAIN ANALYZE
    select Trade_Date, login, sum(profit) as closed_profit, sum(commission) as closed_commission, sum(`swaps`) as closed_swaps
    from `reference`.eod_time eodTime
    join mt4.mt4_trades trades
    on trades.close_time between eodTime.OPEN_TIME and eodTime.CLOSE_TIME
    and trade.cmd in (0,1)
    where eodTime.CLOSE_TIME between @startTime and @endTime
    group by 1,2;
*/

-- EXPLAIN ANALYZE
WITH 
eodTime as (
	select *
    from `reference`.eod_time
    where CLOSE_TIME between @startTime and @endTime
),
trades as (
	select ticket, login, symbol, cmd, open_time, close_time, commission, `swaps`, profit, `comment` 
    from mt4.mt4_trades
    where close_time between @startTime and @endTime
),
daily as (
	select LOGIN, STATEMENT_DATE, PREVIOUS_BALANCE, DEPOSITS, PROFIT_CLOSED, NEW_BALANCE, PROFIT_OPEN, PL
    from mt4.mt4_daily
    where STATEMENT_DATE between @startDate and @endDate
)
select *, TRIM(ROUND(TRD.PROFIT_CLOSED,2))-DAILY.PROFIT_CLOSED
from (
	select Trade_Date, login, sum(profit) as closed_profit, sum(commission) as closed_commission, sum(`swaps`) as closed_swaps, 
		   sum(case when cmd in (0,1) then profit+commission+`swaps` else 0 end) as PROFIT_CLOSED,
           sum(case when cmd not in (0,1) then profit else 0 end) as deposits
	from eodTime
	join trades
	on trades.close_time between eodTime.OPEN_TIME and eodTime.CLOSE_TIME
	group by 1,2
) trd
left join daily
on trd.login = daily.login
and trd.trade_date = daily.statement_date;

