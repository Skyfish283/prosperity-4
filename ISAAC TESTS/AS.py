from datamodel import *
from typing import List
import string
from statistics import *

class Trader:

    # we want to implement AS market making
    def find_reservation_and_spread(self, product: Product, state: TradingState) -> List[float]:
        if state.traderData == '':
            return 10000
        elif state.traderData.count(';') == 0:
            return 10000
        else:
            past_week: List[float] = [float(x) for x in state.traderData.split(';')]
            mid = mean(past_week)
            var = variance(past_week)
            position = state.position.get(product,0)
            gamma = 1e-3
            tprop = 0.95
            
            return mid-var*position*gamma*tprop, 
    
    def run(self, state: TradingState):
        result = {}

        best_ask, best_ask_amount = list(state.order_depths["RAINFOREST_RESIN"].sell_orders.items())[0]
        best_bid, best_bid_amount = list(state.order_depths["RAINFOREST_RESIN"].buy_orders.items())[0]
        orders: List[Order] = []
        # just around right these values def need adjusting -- find through AS
        res, spread = self.find_reservation_and_spread('RAINFOREST_RESIN',state)
        max_ask = round(res-spread)
        min_bid = round(res+spread)

        print(res)
        print(state.traderData)
        if int(best_ask) <= max_ask:

            orders.append(Order("RAINFOREST_RESIN", best_ask, -best_ask_amount))

        if int(best_bid) >= min_bid:

            orders.append(Order("RAINFOREST_RESIN", best_bid, -best_bid_amount))

        result["RAINFOREST_RESIN"] = orders

        traderData = state.traderData
        if traderData == '':
            traderData = str((best_ask+best_bid)/2)
        elif traderData.count(';') < 3:
            traderData += ';' + str((best_ask+best_bid)/2)
        else:
            traderData = traderData[traderData.find(';')+1:]
            traderData += ';' + str((best_ask+best_bid)/2)

        conversions = None
        return result, conversions, traderData
