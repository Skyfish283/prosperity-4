from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string

class Trader:
    
    def run(self, state: TradingState):
        # Only method required. It takes all buy and sell orders for all symbols as an input, and outputs a list of orders to be sent
        # print("traderData: " + state.traderData)
        # print("Observations: " + str(state.observations))
        result = {}

        # for product in state.order_depths:
        #     order_depth: OrderDepth = state.order_depths[product]
        #     orders: List[Order] = []
        #     acceptable_price = 11;  # Participant should calculate this value
        #     print("Acceptable price : " + str(acceptable_price))
        #     print("Buy Order depth : " + str(len(order_depth.buy_orders)) + ", Sell order depth : " + str(len(order_depth.sell_orders)))
    
        #     if len(order_depth.sell_orders) != 0:
        #         best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]
        #         if int(best_ask) < acceptable_price:
        #             print("BUY", str(-best_ask_amount) + "x", best_ask)
        #             orders.append(Order(product, best_ask, -best_ask_amount))
    
        #     if len(order_depth.buy_orders) != 0:
        #         best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]
        #         if int(best_bid) > acceptable_price:
        #             print("SELL", str(best_bid_amount) + "x", best_bid)
        #             orders.append(Order(product, best_bid, -best_bid_amount))
            
        #     result[product] = orders
        best_ask, best_ask_amount = list(state.order_depths["RAINFOREST_RESIN"].sell_orders.items())[0]
        best_bid, best_bid_amount = list(state.order_depths["RAINFOREST_RESIN"].buy_orders.items())[0]
        orders: List[Order] = []
        if int(best_ask) < 9998:
            orders.append(Order("RAINFOREST_RESIN", best_ask, -best_ask_amount))
            print("BUYING " + str(-best_ask_amount) + " SHARES AT ", best_ask)
        if int(best_bid) > 9999:
            orders.append(Order("RAINFOREST_RESIN", best_bid, -best_bid_amount))
            print("SELLING " + str(-best_bid_amount) + " SHARES AT ", best_bid)
        
        result["RAINFOREST_RESIN"] = orders


    
        traderData = "SAMPLE" # String value holding Trader state data required. It will be delivered as TradingState.traderData on next execution.
        
        conversions = 1
        return result, conversions, traderData
