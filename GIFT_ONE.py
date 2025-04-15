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
class DifferenceStrategy(Strategy):
    def __init__(self, symbol: str, limit: int, related_product_weights: Dict[Product,weight]) -> None:
        super().__init__(symbol, limit)
        self.related_product_weights = related_product_weights
    
    def force_buy(self, state : TradingState, quantity: int) -> None:
        ## BUY QUANTITY REGARDLESS OF PRICE (quantity is positive)
        for ask, vol in list(state.order_depths[self.symbol].sell_orders.items()):
            self.buy(ask, min(-vol, quantity))
            quantity -= min(-vol, quantity)
            if quantity <= 0:
                return

    def force_sell(self, state: TradingState, quantity: int) -> None:
        ## SELL QUANTITY REGARDLESS OF PRICE (quantity is positive)
        logger.print("FORCE SELLING", quantity, "of", self.symbol)
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

    def find_diff(self, state: TradingState) -> float:
        real_price = 0
        for product, weight in self.related_product_weights.items():
            p_asks = list(state.order_depths[product].sell_orders.items())
            p_bids = list(state.order_depths[product].buy_orders.items())
            real_price += (p_asks[0][0] + p_bids[0][0]) / 2 * weight

        group_asks = list(state.order_depths[self.symbol].sell_orders.items())
        group_bids = list(state.order_depths[self.symbol].buy_orders.items())
        mid_price = (group_asks[0][0] + group_bids[0][0]) / 2
        
        diff = real_price - mid_price

        logger.print("DIFF", diff, "REAL PRICE", real_price, "MID PRICE", mid_price, "LIMIT", self.limit, "POSITION", state.position.get(self.symbol,0))

        if diff > 98:
            quantity = min(self.limit, self.limit-state.position.get(self.symbol,0))
            self.force_buy(state, quantity)
        elif diff < -56:
            quantity = min(self.limit, self.limit+state.position.get(self.symbol,0))
            self.force_sell(state, quantity)
        elif abs(diff) < 9:
            self.zero_position(state)

class PicnicBasket1Strategy(DifferenceStrategy):
    def __init__(self, symbol: str, limit: int) -> None:
        super().__init__(symbol, limit, {
            "CROISSANTS": 6,
            "JAMS": 3,
            "DJEMBES": 1
        })

class PicnicBasket2Strategy(DifferenceStrategy):
    def __init__(self, symbol: str, limit: int) -> None:
        super().__init__(symbol, limit, {
            "CROISSANTS": 4,
            "JAMS": 2,
        })

class PicnicBasket2Strategy(DifferenceStrategy):
    def __init__(self, symbol: str, limit: int) -> None:
        super().__init__(symbol, limit, {
            "CROISSANTS": 4,
            "JAMS": 2
        })

# Main trader class that coordinates multiple strategies
class Trader:
    def __init__(self) -> None:
        limits = {
            "RAINFOREST_RESIN": 50,
            "KELP": 50,
            "SQUID_INK": 50,
            "CROISSANT": 250,
            "JAM": 350,
            "DJEMBE": 60,
            "PICNIC_BASKET1": 60,
            "PICNIC_BASKET2": 100
        }

        # Instantiate strategies for each symbol
        self.strategies = {
            symbol: strat(symbol, limits[symbol]) 
            for symbol, strat in {
                "PICNIC_BASKET1": PicnicBasket1Strategy,
                "PICNIC_BASKET2": PicnicBasket2Strategy
            }.items()
        }
  
    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        # logger.print(state.position)  # Log current positions

        conversions = 0  # Unused here, placeholder for conversion tracking

        # Load previously saved strategy data
        old_trader_data = json.loads(state.traderData) if state.traderData != "" else {}
        new_trader_data = {}

        result = {}

        for symbol, strategy in self.strategies.items():
            if symbol in old_trader_data:
                strategy.load(old_trader_data.get(symbol, None))

            # Run strategy for each symbol if order book is available
            if symbol in state.order_depths:
                result[symbol] = strategy.run(state)
            
            new_trader_data[symbol] = strategy.save()        


        trader_data = json.dumps(new_trader_data, separators=(",", ":"))

        logger.flush(state, result, conversions, trader_data)

        return result, conversions, trader_data
