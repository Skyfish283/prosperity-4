from datamodel import *
from typing import *
import string
from statistics import *
import math
import json
from collections import deque

class Trader:
    def track_extremes(self, product: str, state: TradingState, data: Dict[str,Dict[str,Any]]):
        asks = list(state.order_depths[product].buy_orders.items())
        bids = list(state.order_depths[product].sell_orders.items())
        mid = (asks[0][0] - bids[0][0])/2
        if data == {}:
            data[product]["last_price"] = mid
            data[product]["diffs"] = deque()
            data[product]["extremes"] = deque()
            data[product]["dir"] = 0
        else:
            data[product]["diffs"].append(mid-data[product]["last_price"])
            if len(data[product]["diffs"]) > 5:
                data[product]["diffs"].popleft()
            up = 0
            down = 0
            for diff in data[product]["diffs"]:
                if diff < 0:
                    down += 1
                elif diff>0:
                    up += 1
            
            if up > down:
                if data[product]["dir"] != 1:
                    data[product]["extremes"].append(mid)
                else:
                    data[product]["extremes"]
                    
            

    
    def run(self, state: TradingState):
        result = {}

        if state.traderData == "":
            data : Dict[str,Dict[str,List[float]]] = {}
        else:
            data : Dict[str,Dict[str,List[float]]] = json.loads(state.traderData)

        product = 'SQUID_INK'

        self.track_extremes(state, data)

        traderData = json.dumps(data)

        print(state.toJSON())

        conversions = None
        return result, conversions, traderData
