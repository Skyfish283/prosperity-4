from datamodel import *
from typing import List
import string
from statistics import *
import math
import json

class Trader:

    # we want to implement AS market making
    def find_reservation_and_spread(self, product: Product, state: TradingState, past_week: List[float]) -> List[float]:
        if past_week == []:
            return None
        elif len(past_week) == 1:
            return past_week[0]
        else:
            mid = mean(past_week)
            var = variance(past_week)
            position = state.position.get(product,0)
            gamma = 1e-3
            tprop = 0.95
            k = math.log(2)/0.01
            
            return mid-var*position*gamma*tprop, 2/gamma*math.log(1+gamma/k)+gamma*var
    
    def run(self, state: TradingState):
        result = {}
        data : Dict[str,List[float]] = json.loads(state.traderData)

        products = ['RAINFOREST_RESIN','KELP']
        for product in products:
            best_ask, best_ask_amount = list(state.order_depths[product].sell_orders.items())[0]
            best_bid, best_bid_amount = list(state.order_depths[product].buy_orders.items())[0]
            orders: List[Order] = []
            # just around right these values def need adjusting -- find through AS
            res, spread = self.find_reservation_and_spread(product,state,data[product])
            spread = min(spread,1)
            max_ask = round(res-spread)
            min_bid = round(res+spread)

            # print(res)
            # print(state.traderData)
            if int(best_ask) <= max_ask:

                orders.append(Order(product, best_ask, -best_ask_amount))

            if int(best_bid) >= min_bid:

                orders.append(Order(product, best_bid, -best_bid_amount))

            result[product] = orders

            # traderData = state.traderData
            # if traderData == '':
            #     traderData = str((best_ask+best_bid)/2)
            # elif traderData.count(',') < 3:
            #     traderData += ',' + str((best_ask+best_bid)/2)
            # else:
            #     traderData = traderData[traderData.find(',')+1:]
            #     traderData += ',' + str((best_ask+best_bid)/2)

        traderData = json.dumps(data)

        conversions = None
        return result, conversions, traderData
