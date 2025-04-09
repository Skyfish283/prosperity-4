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
            return [-1,-1]
        elif len(past_week) == 1:
            return past_week[0],1
        else:
            mid = mean(past_week)
            var = variance(past_week)
            position = state.position.get(product,0)
            gamma = 1e-4
            tprop = 0.95
            k = math.log(2)/0.01
            
            return mid-var*position*gamma*tprop, 2/gamma*math.log(1+gamma/k)+gamma*var
    
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

            if data.get(product, {}) == {}:
                data[product] = {"prev_mid": [(best_ask+best_bid)/2],"past_up":[],"past_down":[]}
            else:
                if data[product]["prev_mid"] > (best_ask+best_bid)/2:
                    data[product]["past_up"].append((best_ask+best_bid)/2-data[product]["prev_mid"])
                elif data[product]["prev_mid"] < (best_ask+best_bid)/2:
                    data[product]["past_down"].append(-((best_ask+best_bid)/2-data[product]["prev_mid"]))
                
                if len(data[product]["past_up"]) > 14:
                    del data[product]["past_up"][0]
                if len(data[product]["past_down"]) > 14:
                    del data[product]["past_down"][0]
                rsi = 100-(100 / (1 + mean(data[product]["past_up"]) / mean(data[product]["past_down"]) ) )

            

            if int(best_ask) <= max_ask:

                orders.append(Order(product, best_ask, -best_ask_amount))

            if int(best_bid) >= min_bid:

                orders.append(Order(product, best_bid, -best_bid_amount))

            result[product] = orders

        traderData = json.dumps(data)

        print(state.toJSON())

        conversions = None
        return result, conversions, traderData
