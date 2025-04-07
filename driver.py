#very incomplete

from trader import Trader
from typing import List, Dict
from datamodel import TradingState, OrderDepth
import pandas as pd

def test(timestamp: int, past_state: TradingState):
    state: TradingState = TradingState(past_state.traderData)

def main():
    test: str = "kelp-1.csv"
    test_data = pd.read_csv(test)
    trader: Trader

class product_day:
    product: str
    buy_price: list[int]
    buy_volume: list[int]
    sell_price: list[int]
    sell_volume: list[int]

    def __init__(self,buy_price: list[int], buy_volume: list[int], sell_price: list[int], sell_volume: list[int]):
        self.buy_price = buy_price
        self.buy_volume = buy_volume
        self.sell_price = sell_price
        self.sell_volume = sell_volume

class day:
    time: int
    products: list[str]
    product_days: Dict[str,product_day]

    def __init__(self, time):
        self.time = time
        self.products = []
        self.product_days = {}



class back_tester:
    test_data: pd.core.frame.DataFrame
    time_stamps: List[int]
    # prod_days: Dict[int, List[product_day]]
    days: Dict[int, day]
    # states: Dict[int,TradingState]
    trader: Trader

    def __init__(self, data_file : str, trader: Trader):
        self.states = {}
        self.trader = trader
        self.test_data = pd.read_csv('data/'+data_file,sep=';')
        self.time_stamps = list(self.test_data['timestamps'].drop_duplicates())
        self.time_stamp = 0
        self.test()

    def unpack_data(self):
        for idx,row in self.test_data.iterrows():
            if row['timestamp'] not in self.days:
                self.days[row['timestamp']] = day(row['timestamp'])
            p = [1,2,3]
            prod = product_day([row['buy_price_'+x] for x in p], [row['buy_volume_'+x] for x in p], [row['sell_price_'+x] for x in p], [row['sell_volume_'+x] for x in p])
            self.days[row['timestamp']].product_days[row['product']] = prod

    def make_trade_state(self, traderData, time) -> TradingState:
        order_depths: Dict[str, OrderDepth]
        for product in self.days[time].products:
            order_depth = OrderDepth()

            dayinfo = self.days[time].product_days[product]
            
            for price,vol in zip(dayinfo.buy_price, dayinfo.buy_volume):
                order_depth.buy_orders[price] = vol
            
            for price,vol in zip(dayinfo.sell_price, dayinfo.sell_volume):
                order_depth.buy_orders[price] = -vol

            order_depths[product] = order_depth


        return TradingState(traderData, time, {}, order_depths,)


    def test(self, state: TradingState):
        traderData = state.traderData
        old_time = state.timestamp

        result, conversions, traderData = self.trader.run(state)


    

if __name__=="__main__":
    initialTrade : TradingState = TradingState("",0,)