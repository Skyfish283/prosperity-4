#very incomplete

from trader import Trader
from typing import List, Dict
from datamodel import TradingState, Listing
import pandas as pd

def test(timestamp: int, past_state: TradingState):
    state: TradingState = TradingState(past_state.traderData)

def main():
    test: str = "kelp-1.csv"
    test_data = pd.read_csv(test)
    trader: Trader

class back_tester:
    test_data: pd.core.frame.DataFrame
    time_stamps: List[int]
    states: Dict[int, TradingState]
    trader: Trader

    def __init__(self, data_file : str):
        self.test_data = pd.read_csv('data/'+data_file,sep=';')
        self.time_stamps = list(self.test_data['timestamps'].drop_duplicates())
        for time in self.time_stamps:
            relevant_frame = self.test_data[self.test_data['timestamp']==time]
            state: TradingState = TradingState()
            state.timestamp = time
            for row in relevant_frame:
                #map stamp to tradingstate
                state.
        self.time_stamp = 0
        self.test()

    def test(self, state: TradingState):
        traderData = state.traderData
        old_time = state.timestamp

        result, conversions, traderData = self.trader.run(state)


    

if __name__=="__main__":
    initialTrade : TradingState = TradingState("",0,)