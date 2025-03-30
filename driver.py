#very incomplete

import trader
from datamodel import TradingState, Listing

if __name__=="__main__":
    ts : TradingState = TradingState("",0,{"RAINFOREST_RESIN": Listing("RAINFOREST_RESIN",)})
    trader.run()