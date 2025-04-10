from datamodel import *
from typing import List, Dict
import string
from statistics import *
import math
import jsonpickle

Product = str
class Trader:

    def run(self, state: TradingState):
        # print("traderData: " + state.traderData)
        # print("Observations: " + str(state.observations))

        tempdata: Dict[Product, List[float]] = {}
        if state.traderData not in [None, "null", ""]:
            tempdata : Dict[Product, List[float]] = jsonpickle.decode(state.traderData)
        result = {}
        MAX_TIMESTAMP = 3000000
        orders: List[Order] = []
        min_sample_size : int = 10
        max_sample_size : int = 20

        init_prices : Dict[Product, float] = {'KELP': 2000, 'RAINFOREST_RESIN': 10000, 'SQUID_INK': 2000}
        init_var : Dict[Product, float] = {'RAINFOREST_RESIN': 2.2387, 'KELP': 5.8579, 'SQUID_INK': 1819.6736}

        for product in state.order_depths:
            # skip squid ink for market making
            if product == "SQUID_INK":
               continue
            order_depth = state.order_depths[product]
            try:
                tempdata[product]
            except KeyError:
                tempdata[product] = []
            if len(tempdata[product]) < min_sample_size:
                mid_price = init_prices[product]
                var = init_var.get(product, 1.0)
                # print("Not enough data, using initial values")
            else:
                past_data = tempdata[product]
                mid_price = mean(past_data)
                var = variance(past_data)
                # print(f"{product} Mid price: {mid_price}, Variance: {var}")

            gamma : float = 1e-3
            quantity = state.position.get(product, 0)
            normalised_time = 1 - max(state.timestamp / MAX_TIMESTAMP, 0.5)
            res_price = mid_price - quantity * gamma * var * normalised_time
            # print(f"Res price for {product}: {res_price}")

            kappa : float = math.log(2) / 0.01
            opt_spread = gamma * var * normalised_time + 2 / gamma * math.log(1+gamma/kappa)

            max_ask : float = res_price - opt_spread / 2
            min_bid : float = res_price + opt_spread / 2

            best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]
            best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]

            if int(best_ask) <= max_ask: # and (state.position.get(product, 0) - best_ask_amount) < 50:
                if (state.position.get(product, 0) - best_ask_amount) > 50:
                    best_ask_amount = state.position.get(product, 0) - 50
                # print(f"BUY {str(-best_ask_amount)} {product} AT {best_ask}")
                orders.append(Order(product, best_ask, -best_ask_amount))
            if int(best_bid) >= min_bid: # and (state.position.get(product, 0) - best_bid_amount) < -50:
                if (state.position.get(product, 0) - best_bid_amount) < -50:
                   best_bid_amount = state.position.get(product, 0) + 50
                # print(f"SELL {str(best_bid_amount)} {product} AT {best_bid}")
                orders.append(Order(product, best_bid, -best_bid_amount))

            if len(tempdata[product]) > max_sample_size:
                tempdata[product] = tempdata[product][1:]
                tempdata[product].append((best_ask + best_bid) / 2)
            else:
                tempdata[product].append((best_ask + best_bid) / 2)

            result[product] = orders
        traderData = jsonpickle.encode(tempdata)
        conversions = None
        return result, conversions, traderData
        
