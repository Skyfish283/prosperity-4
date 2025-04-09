from datamodel import *
from typing import List
import string
from statistics import *
import math
import json

class Trader:
    
    def run(self, state: TradingState):
        result = {}

        product = "RAINFOREST_RESIN"
        asks = list(state.order_depths[product].sell_orders.items())
        bids = list(state.order_depths[product].buy_orders.items())
        best_ask = asks[0][0]
        best_bid = bids[0][0]

        orders: List[Order] = []

        ideal_pos = 25*(9999-(best_bid+best_ask)/2)

        diff = ideal_pos-state.position.get(product,0)

        if diff > 50:
            diff = 50
        if diff < -50:
            diff = -50

        


        if diff>0:
            for bid,amt in bids:
                if (diff<=0):
                    continue
                orders.append(Order(product, bid, max(amt,diff)))
                diff -= amt
        else:
            for ask,amt in asks:
                if (diff>=0):
                    continue
                orders.append(Order(product, ask, min(amt,diff)))
                diff += amt

        result[product] = orders

        print(state.toJSON())

        traderData = ""

        conversions = None
        return result, conversions, traderData
