import json
from abc import abstractmethod
from collections import deque
from datamodel import *
from typing import *
import pandas as pd

MACDsignals = List[int]

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )

        # We truncate state.traderData, trader_data, and self.logs to the same max. length to fit the log limit
        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self.to_json(
                [
                    self.compress_state(state, self.truncate(state.traderData, max_item_length)),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])

        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]

        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )

        return compressed

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice,
                observation.sunlightIndex,
            ]

        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])

        return compressed

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value

        return value[: max_length - 3] + "..."


logger = Logger()


class Strategy:
    def __init__(self, symbol: str, limit: int) -> None:
        self.symbol = symbol  # The trading symbol
        self.limit = limit    # Max allowable position for the symbol

    @abstractmethod
    def act(self, state: TradingState) -> None:
        # Subclasses must implement trading logic here
        raise NotImplementedError()

    def run(self, state: TradingState) -> list[Order]:
        # Executes the strategy and returns a list of orders
        self.orders = []
        self.act(state)
        return self.orders

    def buy(self, price: int, quantity: int) -> None:
        # Appends a buy order to the orders list
        self.orders.append(Order(self.symbol, price, quantity))

    def sell(self, price: int, quantity: int) -> None:
        # Appends a sell order (negative quantity) to the orders list
        self.orders.append(Order(self.symbol, price, -quantity))

    def save(self):
        # Optional: Save internal state (for persistent memory between runs)
        return None

    def load(self, data) -> None:
        # Optional: Load internal state from saved data
        pass

weight = int

class MacaronStrategy(Strategy):
    def __init__(self, symbol: str, limit: int) -> None:
        super().__init__(symbol, limit)
        self.conversions = 0
    
    def force_buy(self, state : TradingState, quantity: int) -> None:
        ## BUY QUANTITY REGARDLESS OF PRICE (quantity is positive)
        for ask, vol in list(state.order_depths[self.symbol].sell_orders.items()):
            self.buy(ask, min(-vol, quantity))
            quantity -= min(-vol, quantity)
            if quantity <= 0:
                return

    def force_sell(self, state: TradingState, quantity: int) -> None:
        ## SELL QUANTITY REGARDLESS OF PRICE (quantity is positive)
        # logger.print("FORCE SELLING", quantity, "of", self.symbol)
        for bid, vol in list(state.order_depths[self.symbol].buy_orders.items()):
            self.sell(bid, min(vol, quantity))
            quantity -= min(vol, quantity)
            if quantity <= 0:
                return
            
    def zero_position(self, state: TradingState) -> None:
        if state.position.get(self.symbol,0) > 0:
            self.force_sell(state, state.position.get(self.symbol,0))
        elif state.position.get(self.symbol,0) < 0:
            self.force_buy(state, -state.position.get(self.symbol,0))

    def get_real_price(self, state: TradingState) -> float:
        return 2.77*state.observations.conversionObservations[self.symbol].sugarPrice - 3.12*state.observations.conversionObservations[self.symbol].sunlightIndex + 275.7

    def get_market_price(self, state: TradingState) -> float:
        group_asks = list(state.order_depths[self.symbol].sell_orders.items())
        group_bids = list(state.order_depths[self.symbol].buy_orders.items())
        return (group_asks[0][0] + group_bids[0][0]) / 2
    
    def act(self, state: TradingState) -> None:
        real_price = self.get_real_price(state)
        mid_price = self.get_market_price(state)
        
        diff = round(real_price - mid_price)

        self.conversions = 0

        # print(self.symbol, ' + ', state.position.get(self.symbol,0))

        if diff > 70:
            quantity = min(self.limit, self.limit-state.position.get(self.symbol,0))
            self.force_buy(state, quantity)
        elif diff > 35:
            quantity = min(self.limit, self.limit//2-state.position.get(self.symbol,0))
            self.force_buy(state, quantity)
        elif diff < -70:
            self.conversions = -10
            # print("CONVERTING -10")
        elif diff < -35:
            self.conversions = -5
        elif abs(diff) < 10:
            if state.position.get(self.symbol,0) > 0:
                self.conversions = max(-10,-state.position.get(self.symbol,0))
            else:
                self.zero_position(state)





# Main trader class that coordinates multiple strategies
class Trader:
    def __init__(self) -> None:
        limits = {
            "MAGNIFICENT_MACARONS": 75
        }

        # Instantiate strategies for each symbol
        self.strategies = {
            symbol: strat(symbol, limits[symbol]) 
            for symbol, strat in {
                "MAGNIFICENT_MACARONS" : MacaronStrategy
            }.items()
        }

    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:

        old_trader_data = json.loads(state.traderData) if state.traderData != "" else {}
        new_trader_data = {}

        result = {}

        for symbol, strategy in self.strategies.items():
            if symbol in old_trader_data:
                strategy.load(old_trader_data.get(symbol, None))

            if symbol in state.order_depths:
                result[symbol] = strategy.run(state)
            
            new_trader_data[symbol] = strategy.save()        


        trader_data = json.dumps(new_trader_data, separators=(",", ":"))

        conversions = self.strategies['MAGNIFICENT_MACARONS'].conversions

        logger.flush(state, result, conversions, trader_data)

        return result, conversions, trader_data
