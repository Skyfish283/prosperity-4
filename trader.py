from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
from statistics import *

class Trader:

    # we want to implement AS market making
    def find_reservation(state: TradingState) -> int:
        return 0
    
    def run(self, state: TradingState):
        result = {}

        best_ask, best_ask_amount = list(state.order_depths["RAINFOREST_RESIN"].sell_orders.items())[0]
        best_bid, best_bid_amount = list(state.order_depths["RAINFOREST_RESIN"].buy_orders.items())[0]
        orders: List[Order] = []
        # just around right these values def need adjusting -- find through AS
        # MAX_ASK = 9999
        # MIN_BID = 10001
        # if int(best_ask) < MAX_ASK:
        #     orders.append(Order("RAINFOREST_RESIN", best_ask, -best_ask_amount))
        #     print("BUYING " + str(-best_ask_amount) + " SHARES AT ", best_ask)
        # if int(best_bid) > MIN_BID:
        #     orders.append(Order("RAINFOREST_RESIN", best_bid, -best_bid_amount))
        #     print("SELLING " + str(-best_bid_amount) + " SHARES AT ", best_bid)
        orders.append(Order("RAINFOREST_RESIN", 9998, 25))
        orders.append(Order("RAINFOREST_RESIN", 10002, -25))
        result["RAINFOREST_RESIN"] = orders
        traderData = state.traderData
        '''
        result["RAINFOREST_RESIN"] = orders
        traderData = state.traderData
        if traderData.count(';') < 4:
            traderData += ';' + str()'
        '''
        print(str(state.market_trades))
        conversions = None
        return result, conversions, traderData
