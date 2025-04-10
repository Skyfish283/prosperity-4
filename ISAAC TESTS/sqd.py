from datamodel import *
from typing import List
import string
from statistics import *
import math
import json

class Trader:
    def ave(self, product: str, data : List[float]):
        return mean(data)

    
    def run(self, state: TradingState):
        result = {}

        if state.traderData == "":
            data : Dict[str,Dict[str,List[float]]] = {}
        else:
            data : Dict[str,Dict[str,List[float]]] = json.loads(state.traderData)

        products = ['SQUID_INK']

        for product in products:
            best_ask, best_ask_amount = list(state.order_depths[product].sell_orders.items())[0]
            best_bid, best_bid_amount = list(state.order_depths[product].buy_orders.items())[0]

            if data.get(product, []) == []:
                data[product]["past_week"] = [(best_ask+best_bid)/2]
            else:
                data[product]["past_week"].append((best_ask+best_bid)/2)

            if (len(data[product]) > 14):
                del data[product][0]

            orders: List[Order] = []
            # just around right these values def need adjusting -- find through AS
            res, spread = self.find_reservation_and_spread(product,state,data[product]["past_week"])

            if (res == -1):
                res = (best_ask+best_bid)/2
                spread = 1

            spread = min(spread,1)
            max_ask = round(res-spread)
            min_bid = round(res+spread)

            # print(res)
            # print(state.traderData)
            if state.position > 0:
                orders.append()

            if int(best_bid) >= min_bid:

                orders.append(Order(product, best_bid, -best_bid_amount))

            result[product] = orders

        traderData = json.dumps(data)

        print(state.toJSON())

        conversions = None
        return result, conversions, traderData
