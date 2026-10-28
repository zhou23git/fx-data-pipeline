        SELECT ord.ORDER_ID, ord.CONNECTOR, ord.ACCOUNT, ord.SYMBOL, sym.digits,
			   ord.SIDE, SUBID1, SUBID2, SUBID3, SUBID4,
               ord.FILLPRICE as OrderFillPrice,
               leg.LEG_ID, b_book, LP, Markup_Bid, Markup_Ask, leg.fillsize as LegFillSize, fillprice1, fillprice2,
               mt4.FILLPRICE as DonePrice
        FROM xcore.xcore_order ord
        left join reference.xcore_symbol_reference sym
        on ord.symbol = sym.xcore_symbol
        left join xcore.xcore_leg leg
        on ord.order_id = leg.order_id
        left join xcore.xcore_order_mt4 mt4
        on ord.SUBID2 = mt4.CLORDID
        where leg.fillsize > 0;