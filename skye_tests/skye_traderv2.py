import json
from abc import abstractmethod
from collections import deque
from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
from typing import Any

# JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None


# Base strategy class for all trading strategies
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


# A general market-making strategy with inventory management
class MarketMakingStrategy(Strategy):
    def __init__(self, symbol: Symbol, limit: int) -> None:
        super().__init__(symbol, limit)
        self.window = deque()  # Tracks recent extreme positions
        self.window_size = 10  # Number of ticks to track for liquidation logic

    @abstractmethod
    def get_true_value(state: TradingState) -> int:
        # Subclasses define how to compute the asset's true value
        #for kelp the true value will be the mid price of best ask and best bid
        #for resin its assumed to be constant around 10000
        #for squid ink
        raise NotImplementedError()

    def act(self, state: TradingState) -> None:
        true_value = self.get_true_value(state)  # Estimated fair price of the asset

        order_depth = state.order_depths[self.symbol]
        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True)  # Highest bid first
        sell_orders = sorted(order_depth.sell_orders.items())              # Lowest ask first

        position = state.position.get(self.symbol, 0)
        to_buy = self.limit - position   # Remaining capacity to buy
        to_sell = self.limit + position  # Remaining capacity to sell

        # Update window with whether position has hit the limit
        self.window.append(abs(position) == self.limit)
        if len(self.window) > self.window_size:
            self.window.popleft()

        # Liquidation logic: based on how frequently we're stuck at max position
        soft_liquidate = (
            len(self.window) == self.window_size and 
            sum(self.window) >= self.window_size / 2 and 
            self.window[-1]
        )
        hard_liquidate = len(self.window) == self.window_size and all(self.window)

        # Adjust pricing aggression based on current position
        max_buy_price = true_value - 1 if position > self.limit * 0.5 else true_value
        min_sell_price = true_value + 1 if position < self.limit * -0.5 else true_value

        # Try to buy from the order book (market making logic)
        for price, volume in sell_orders:
            if to_buy > 0 and price <= max_buy_price:
                quantity = min(to_buy, -volume)
                self.buy(price, quantity)
                to_buy -= quantity

        # Fallback buy actions if inventory is too empty
        if to_buy > 0 and hard_liquidate:
            self.buy(true_value, to_buy // 2)#floor division
            to_buy -= to_buy // 2

        if to_buy > 0 and soft_liquidate:
            self.buy(true_value - 2, to_buy // 2)
            to_buy -= to_buy // 2

        # Final fallback: aggressive bid just above popular buy price
        if to_buy > 0:
            popular_buy_price = max(buy_orders, key=lambda tup: tup[1])[0]
            price = min(max_buy_price, popular_buy_price + 1)
            self.buy(price, to_buy)

        # Try to sell into the order book
        for price, volume in buy_orders:
            if to_sell > 0 and price >= min_sell_price:
                quantity = min(to_sell, volume)
                self.sell(price, quantity)
                to_sell -= quantity

        # Fallback sell actions if inventory is too full
        if to_sell > 0 and hard_liquidate:
            self.sell(true_value, to_sell // 2)
            to_sell -= to_sell // 2

        if to_sell > 0 and soft_liquidate:
            self.sell(true_value + 2, to_sell // 2)
            to_sell -= to_sell // 2

        # Final fallback: aggressive ask just below popular sell price
        if to_sell > 0:
            popular_sell_price = min(sell_orders, key=lambda tup: tup[1])[0]
            price = max(min_sell_price, popular_sell_price - 1)
            self.sell(price, to_sell)

    def save(self):
        # Save the liquidation window for state persistence
        return list(self.window)

    def load(self, data) -> None:
        # Restore the liquidation window from saved state
        self.window = deque(data[0])


# Strategy for resin: assumes a fixed fair value
class ResinStrategy(MarketMakingStrategy):
    def get_true_value(self, state: TradingState) -> int:
        return 10_000  # Assumes constant fair value


# Strategy for kelp: calculates fair value based on market depth (vol is prioritzied)
class KelpStrategy(MarketMakingStrategy):
    def get_true_value(self, state: TradingState) -> int:
        order_depth = state.order_depths[self.symbol]
        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True) #highest to lowest
        sell_orders = sorted(order_depth.sell_orders.items())#lowest to highest

        popular_buy_price = max(buy_orders, key=lambda tup: tup[1])[0] #find the maximum based on volume
        popular_sell_price = min(sell_orders, key=lambda tup: tup[1])[0]

        return round((popular_buy_price + popular_sell_price) / 2)  # Mid-price

# Strategy for Squid Ink: ********
class SquidInkStrategy(MarketMakingStrategy):
    def increaseCheck(self)->bool:
        increase = True
        return increase
    def get_true_value(self, state: TradingState) -> int:
        order_depth = state.order_depths[self.symbol]
        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True) #highest to lowest
        sell_orders = sorted(order_depth.sell_orders.items())#lowest to highest

        popular_buy_price = max(buy_orders, key=lambda tup: tup[1])[0] #find the maximum based on volume
        popular_sell_price = min(sell_orders, key=lambda tup: tup[1])[0]
        return round((popular_buy_price + popular_sell_price) / 2)+1 if self.increaseCheck()==True else round((popular_buy_price + popular_sell_price) / 2)-1 # Mid-price


# Main trader class that coordinates multiple strategies
class Trader:
    def __init__(self) -> None:
        limits = {
            "RAINFOREST_RESIN": 50,
            "KELP": 50,
            "SQUID_INK": 50
        }

        # Instantiate strategies for each symbol
        self.strategies = {
            "RAINFOREST_RESIN": ResinStrategy("RAINFOREST_RESIN",50),
            "KELP": KelpStrategy("KELP",50),
            "SQUID_INK":SquidInkStrategy("SQUID_INK",50)
        }

    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        # logger.print(state.position)  # Log current positions

        conversions = 0  # Unused here, placeholder for conversion tracking

        # Load previously saved strategy data
        old_trader_data = json.loads(state.traderData) if state.traderData != "" else {}
        new_trader_data = []#list of two dictionaries: window and past data

        orders = {}
        for symbol, strategy in self.strategies.items():
            if symbol in old_trader_data[0]:
                strategy.load(old_trader_data[0].get(symbol, None))

            # Run strategy for each symbol if order book is available
            if symbol in state.order_depths:
                #update past data if squid ink
                if symbol == "SQUID_INK":
                    past_prices = old_trader_data[1].get(symbol, [])
                    if past_prices == []:
                        old_trader_data[1][symbol]= []
                    best_ask, best_ask_amount = list(state.order_depth.sell_orders.items())[0]
                    best_bid, best_bid_amount = list(state.order_depth.buy_orders.items())[0]
                    old_trader_data[1][symbol].append((best_ask+best_bid)/2)
                    max_past_data = 10
                    if len(past_prices) > max_past_data:
                        past_prices = past_prices[-max_past_data:] #control under max data size
                        old_trader_data[1][symbol] = past_prices
                    orders[symbol] = strategy.run(state)

            new_trader_data[0][symbol] = strategy.save()
            new_trader_data[1] =  old_trader_data[1]

        # Serialize internal state for next run
        trader_data = json.dumps(new_trader_data, separators=(",", ":"))

        # logger.flush(state, orders, conversions, trader_data)
        return orders, conversions, trader_data
