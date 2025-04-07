#very incomplete

from trader import Trader
from typing import List, Dict
from datamodel import *
import pandas as pd
from dataclasses import dataclass

def test(timestamp: int, past_state: TradingState):
    state: TradingState = TradingState(past_state.traderData)

def main():
    test: str = "kelp-1.csv"
    test_data = pd.read_csv(test)
    trader: Trader

@dataclass
class product_day:
    product: str
    buy_price: list[int]
    buy_volume: list[int]
    sell_price: list[int]
    sell_volume: list[int]

class day:
    time: int
    products: list[str]
    product_days: Dict[str,product_day]

    def __init__(self, time):
        self.time = time
        self.products = []
        self.product_days = {}

@dataclass
class MarketTrade:
    trade: Trade
    sell: int
    buy: int



class back_tester:
    test_data: pd.core.frame.DataFrame
    trade_data: pd.core.frame.DataFrame
    time_stamps: List[int]
    all_products: List[str]
    # prod_days: Dict[int, List[product_day]]
    days: Dict[int, day]
    trades : Dict[int, Dict[str,List[MarketTrade]]] # trades of given 
    # states: Dict[int,TradingState]
    trader: Trader
    ourTrades: List[Trade]
    profit_loss: int

    def __init__(self, round: int, day: int, trader: Trader):
        self.states = {}
        self.trader = trader
        self.test_data = pd.read_csv('data/round-'+round+'-island-data-bottle/prices_round_'+round+'_day_'+day,sep=';')
        self.trade_data = pd.read_csv('data/round-'+round+'-island-data-bottle/trades_round_'+round+'_day_'+day,sep=';')
        self.time_stamps = list(self.test_data['timestamps'].drop_duplicates())
        self.all_products = list(self.test_data['products'].drop_duplicates())
        self.profit_loss = 0

    def unpack_data(self) -> None:
        for idx,row in self.test_data.iterrows():
            if row['timestamp'] not in self.days:
                self.days[row['timestamp']] = day(row['timestamp'])
            p = [1,2,3]
            prod = product_day([row['buy_price_'+x] for x in p], [row['buy_volume_'+x] for x in p], [row['sell_price_'+x] for x in p], [row['sell_volume_'+x] for x in p])
            self.days[row['timestamp']].product_days[row['product']] = prod

        
        for idx,row in self.trade_data.iterrows():
            trade : Trade = Trade(row['product'],row['price'],row['quantity'],row['buyer'],row['seller'],row['timestamp'])
            market_trade = MarketTrade(trade, row['quantity'], ['quantity'])
            self.trades[row['timestamp']][row['product']].append(market_trade)

            '''
            class Trade:

            def __init__(self, symbol: Symbol, price: int, quantity: int, buyer: UserId=None, seller: UserId=None, timestamp: int=0) -> None:
                self.symbol = symbol
                self.price: int = price
                self.quantity: int = quantity
                self.buyer = buyer
                self.seller = seller
                self.timestamp = timestamp
            '''
    
    def match_sell_order(self, state: TradingState, order: Order) -> list[Trade]:
        trades = []

        order_depth = state.order_depths[order.symbol]
        price_matches = sorted((price for price in order_depth.buy_orders.keys() if price >= order.price), reverse=True)
        for price in price_matches:
            volume = min(abs(order.quantity), order_depth.buy_orders[price])

            trades.append(Trade(order.symbol, price, volume, "", "SUBMISSION", state.timestamp))

            state.position[order.symbol] = state.position.get(order.symbol, 0) - volume
            self.profit_loss[order.symbol] += price * volume

            order_depth.buy_orders[price] -= volume
            if order_depth.buy_orders[price] == 0:
                order_depth.buy_orders.pop(price)

            order.quantity += volume
            if order.quantity == 0:
                return trades

        for market_trade in self.trades[state.timestamp][order.symbol]:
            if market_trade.buy == 0 or market_trade.trade.price < order.price:
                continue

            volume = min(abs(order.quantity), market_trade.buy)

            trades.append(Trade(order.symbol, order.price, volume, market_trade.trade.buyer, "SUBMISSION", state.timestamp))

            state.position[order.symbol] = state.position.get(order.symbol, 0) - volume
            self.profit_loss[order.symbol] += order.price * volume

            market_trade.buy -= volume

            order.quantity += volume
            if order.quantity == 0:
                return trades

        return trades
    
    def match_buy_order(self,state: TradingState, order: Order) -> list[Trade]:
        trades = []

        order_depth = state.order_depths[order.symbol]
        price_matches = sorted(price for price in order_depth.buy_orders.keys() if price <= order.price)
        for price in price_matches:
            volume = min(abs(order.quantity), order_depth.buy_orders[price])

            trades.append(Trade(order.symbol, price, volume, "", "SUBMISSION", state.timestamp))

            state.position[order.symbol] = state.position.get(order.symbol, 0) + volume
            self.profit_loss[order.symbol] -= price * volume

            order_depth.buy_orders[price] += volume
            if order_depth.buy_orders[price] == 0:
                order_depth.buy_orders.pop(price)

            order.quantity -= volume
            if order.quantity == 0:
                return trades

        for market_trade in self.trades[state.timestamp][order.symbol]:
            if market_trade.sell == 0 or market_trade.trade.price > order.price:
                continue

            volume = min(abs(order.quantity), market_trade.sell)

            trades.append(Trade(order.symbol, order.price, volume, "SUBMISSION", market_trade.trade.seller, state.timestamp))

            state.position[order.symbol] = state.position.get(order.symbol, 0) + volume
            self.profit_loss[order.symbol] -= order.price * volume

            market_trade.sell -= volume

            order.quantity -= volume
            if order.quantity == 0:
                return trades

        return trades
    
    def match_order(self, state: TradingState, order: Order):
        if order.quantity > 0:
            self.match_buy_order(state, order)
        elif order.quantity < 0:
            self.match_sell_order(state,order)
        else:
            return []

    def match_orders(self, state: TradingState, orders: Dict[str,List[Order]]):
        for product in self.all_products:
            for order in orders.get(product,[]):
                self.ourTrades.extend(self.match_order(state,order))


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