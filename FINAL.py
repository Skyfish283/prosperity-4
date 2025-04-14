import json
from abc import abstractmethod
from collections import deque
from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
from typing import *
import pandas as pd

MACDsignals = List[int]

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
            self.buy(true_value, to_buy // 2)
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
        self.window = deque(data)



class ResinStrategy(MarketMakingStrategy):
    def get_true_value(self, state: TradingState) -> int:
        return 10_000  # Assumes constant fair value



class KelpStrategy(MarketMakingStrategy):
    def get_true_value(self, state: TradingState) -> int:
        order_depth = state.order_depths[self.symbol]
        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True)
        sell_orders = sorted(order_depth.sell_orders.items())

        popular_buy_price = max(buy_orders, key=lambda tup: tup[1])[0]
        popular_sell_price = min(sell_orders, key=lambda tup: tup[1])[0]

        return round((popular_buy_price + popular_sell_price) / 2)  # Mid-price


# Main trader class that coordinates multiple strategies
class Trader:
    def __init__(self) -> None:
        limits = {
            "RAINFOREST_RESIN": 50,
            "KELP": 50,
        }

        # Instantiate strategies for each symbol
        self.strategies = {
            symbol: clazz(symbol, limits[symbol]) 
            for symbol, clazz in {
                "RAINFOREST_RESIN": ResinStrategy,
                "KELP": KelpStrategy,
            }.items()
        }

    def MACD(self, state: TradingState, past_data: List[float], ema_fast: int=12, 
             ema_slow: int=26, ema_sig: int=9) -> MACDsignals:
        # signal-line crossover, zero crossover and divergence respectively
        signals : MACDsignals = [0, 0, 0]
        if len(past_data) < (ema_fast + ema_slow + 1):
            return signals
        ema_fast = pd.Series(past_data).ewm(span=ema_fast, adjust=False).mean()
        ema_slow = pd.Series(past_data).ewm(span=ema_slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=ema_sig, adjust=False).mean()
        hist = macd - signal
        # will implement lookback later
        # signal-line crossover
        if hist.iloc[-1] > 0 and hist.iloc[-2] < 0:
            signals[0] = 1
        elif hist.iloc[-1] < 0 and hist.iloc[-2] > 0:
            signals[0] = -1
        else:
            signals[0] = 0
        # zero crossover
        if macd.iloc[-1] > 0 and macd.iloc[-2] < 0:
            signals[1] = 1
        elif macd.iloc[-1] < 0 and macd.iloc[-2] > 0:
            signals[1] = -1
        else:
            signals[1] = 0
        # divergence
        if past_data[-1] == max(past_data) and macd.iloc[-1] < macd.max():
            signals[2] = -1
        elif past_data[-1] == min(past_data) and macd.iloc[-1] > macd.min():
            signals[2] = 1
        else:
            signals[2] = 0
        return signals
    
    def signal_interpretation(self, state: TradingState, signals: MACDsignals, product, max_pos=50) -> int:
        curr_pos = state.position.get(product, 0)
        if signals[2] != 0:
            return curr_pos + signals[2] * 3
        if signals[0] == 1 and signals[1] == 1:
            return curr_pos + 2
        if signals[0] == 1 and signals[1] == 0:
            return curr_pos + 1
        if signals[0] == 1 and signals[1] == -1:
            return curr_pos # pathological case
        if signals[0] == 0 and signals[1] == 1:
            return curr_pos
        if signals[0] == 0 and signals[1] == 0:
            return state.position.get(product, 0)
        if signals[0] == 0 and signals[1] == -1:
            return curr_pos
        if signals[0] == -1 and signals[1] == 1:
            return curr_pos # pathological case
        if signals[0] == -1 and signals[1] == 0:
            return curr_pos - 1
        if signals[0] == -1 and signals[1] == -1:
            return curr_pos - 2
        
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
    
    def act(self, state: TradingState) -> None:
        real_price = 0
        for product, weight in self.related_product_weights.items():
            p_asks = list(state.order_depths[product].sell_orders.items())
            p_bids = list(state.order_depths[product].buy_orders.items())
            real_price += (p_asks[0][0] + p_bids[0][0]) / 2 * weight

        group_asks = list(state.order_depths[self.symbol].sell_orders.items())
        group_bids = list(state.order_depths[self.symbol].buy_orders.items())
        mid_price = (group_asks[0][0] + group_bids[0][0]) / 2
        
        diff = real_price - mid_price

        # logger.print("DIFF", diff, "REAL PRICE", real_price, "MID PRICE", mid_price, "LIMIT", self.limit, "POSITION", state.position.get(self.symbol,0))

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
            "JAMS": 2
        })


    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        # logger.print(state.position)  # Log current positions

        conversions = 0  # Unused here, placeholder for conversion tracking

        # Load previously saved strategy data
        old_trader_data = json.loads(state.traderData) if state.traderData != "" else {}
        new_trader_data = {}

        result = {}
        

        if old_trader_data.get("SQUID_INK",[]) == []:
            new_trader_data = {"SQUID_INK": []}
        # result = {}
        orders: List[Order] = []

        order_depth = state.order_depths["SQUID_INK"]

        MACD_signals = self.MACD(state, old_trader_data.get("SQUID_INK",[]))
        ideal_pos = self.signal_interpretation(state, MACD_signals, "SQUID_INK")

        pos_diff = max(min(ideal_pos - state.position.get("SQUID_INK", 0), 50), -50)
        if pos_diff > 0:
            for ask, vol in list(order_depth.sell_orders.items()):
                orders.append(Order("SQUID_INK", ask, min(-vol, pos_diff)))
                pos_diff -= min(-vol, pos_diff)
                if pos_diff <= 0:
                    break
        elif pos_diff < 0:
            for bid, vol in list(order_depth.buy_orders.items()):
                orders.append(Order("SQUID_INK", bid, max(-vol, pos_diff)))
                pos_diff += max(-vol, pos_diff)
                if pos_diff >= 0:
                    break
        
        best_ask = list(order_depth.sell_orders.items())[0][0]
        best_bid = list(order_depth.buy_orders.items())[0][0]
        max_sample_size = 100
        product = "SQUID_INK"
        if len(old_trader_data.get(product, [])) > max_sample_size:
            new_trader_data[product] = old_trader_data[product][1:]
            new_trader_data[product].append((best_ask + best_bid) / 2)
        else:
            new_trader_data[product] = old_trader_data.get(product, []).copy()
            new_trader_data[product].append((best_ask + best_bid) / 2)

        for symbol, strategy in self.strategies.items():
            if symbol in old_trader_data:
                strategy.load(old_trader_data.get(symbol, None))

            # Run strategy for each symbol if order book is available
            if symbol in state.order_depths:
                result[symbol] = strategy.run(state)
            
            new_trader_data[symbol] = strategy.save()

        result[product] = orders

        


        trader_data = json.dumps(new_trader_data, separators=(",", ":"))


        return result, conversions, trader_data
