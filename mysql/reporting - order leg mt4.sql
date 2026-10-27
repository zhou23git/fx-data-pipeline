SELECT ord.ORDER_ID, ord.SYMBOL, ord.SIDE, SUBID1, SUBID2, SUBID3, ord.AMOUNT as OrderRequesttAmount, ord.PRICE as OrderRequestPrice, ord.FILLPRICE as OrderFillPrice,
	   leg.LEG_ID, b_book, LP, leg.AMOUNT as LegRequestAmount, leg.price as LegRequestPrice, Markup_Bid, Markup_Ask, leg.fillsize as LegFillSize, fillprice1, fillprice2,
       mt4.PRICE as MT4RequestPrice, mt4.FILLPRICE as DonePrice
FROM xcore.xcore_order ord
left join xcore.xcore_leg leg
on ord.order_id = leg.order_id
left join xcore.xcore_order_mt4 mt4
on ord.SUBID2 = mt4.CLORDID;