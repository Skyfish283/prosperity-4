from datamodel import *

class Trader:    
    def run(self, state: TradingState):
        result = {}
        traderData = ""
        print(state.toJSON())
        conversions = None
        return result, conversions, traderData
