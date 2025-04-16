import json
from abc import abstractmethod
from collections import deque
from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
from typing import *
from statistics import *
import pandas as pd
import numpy as np
import math

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

class MACD(Strategy):
    def __init__(self, symbol, limit, max_sample_size):
        super().__init__(symbol, limit)
        self.past_data: List[float] = []
        self.max_sample_size = max_sample_size

    def load(self, data: List[float]) -> None:
        self.past_data = data

    def save(self):
        return self.past_data

    # AUXILLARY FUNCTIONS
    def MACD(self, state: TradingState, ema_fast: int=12, 
        ema_slow: int=26, ema_sig: int=9) -> MACDsignals:
        # signal-line crossover, zero crossover and divergence respectively
        signals : MACDsignals = [0, 0, 0]
        if self.past_data is None or len(self.past_data) < (ema_fast + ema_slow + 1):
            return signals
        ema_fast = pd.Series(self.past_data).ewm(span=ema_fast, adjust=False).mean()
        ema_slow = pd.Series(self.past_data).ewm(span=ema_slow, adjust=False).mean()
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
        if self.past_data[-1] == max(self.past_data) and macd.iloc[-1] < macd.max():
            signals[2] = -1
        elif self.past_data[-1] == min(self.past_data) and macd.iloc[-1] > macd.min():
            signals[2] = 1
        else:
            signals[2] = 0
        return signals
    
    def signal_interpretation(self, state: TradingState, signals: MACDsignals) -> int:
        curr_pos = state.position.get(self.symbol, 0)
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
            return state.position.get(self.symbol, 0)
        if signals[0] == 0 and signals[1] == -1:
            return curr_pos
        if signals[0] == -1 and signals[1] == 1:
            return curr_pos # pathological case
        if signals[0] == -1 and signals[1] == 0:
            return curr_pos - 1
        if signals[0] == -1 and signals[1] == -1:
            return curr_pos - 2
    
    def act(self, state: TradingState) -> None:
        order_depth = state.order_depths[self.symbol]

        MACD_signals = self.MACD(state)
        ideal_pos = self.signal_interpretation(state, MACD_signals)

        pos_diff = max(min(ideal_pos - state.position.get(self.symbol, 0), 50), -50)
        if pos_diff > 0:
            for ask, vol in list(order_depth.sell_orders.items()):
                self.buy(ask,min(-vol, pos_diff))

                pos_diff -= min(-vol, pos_diff)
                if pos_diff <= 0:
                    break

        elif pos_diff < 0:
            for bid, vol in list(order_depth.buy_orders.items()):
                self.sell(bid,min(vol,-pos_diff))
                pos_diff += max(-vol, pos_diff)
                if pos_diff >= 0:
                    break
        
        best_ask = list(order_depth.sell_orders.items())[0][0]
        best_bid = list(order_depth.buy_orders.items())[0][0]
        if len(self.past_data) > self.max_sample_size:
            self.past_data = self.past_data[1:]
            self.past_data.append((best_ask + best_bid) / 2)
        else:
            self.past_data.append((best_ask + best_bid) / 2)
        
    
class SquidStrategy(MACD):
    def __init__(self, symbol: str, limit: int):
        super().__init__(symbol,limit,100)


# Strategy for Resin: assumes a fixed fair value
class ResinStrategy(MarketMakingStrategy):
    def get_true_value(self, state: TradingState) -> int:
        return 10_000  # Assumes constant fair value


# Strategy for Kelp: calculates fair value based on market depth
class KelpStrategy(MarketMakingStrategy):
    def get_true_value(self, state: TradingState) -> int:
        order_depth = state.order_depths[self.symbol]
        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True)
        sell_orders = sorted(order_depth.sell_orders.items())

        popular_buy_price = max(buy_orders, key=lambda tup: tup[1])[0]
        popular_sell_price = min(sell_orders, key=lambda tup: tup[1])[0]

        return round((popular_buy_price + popular_sell_price) / 2)  # Mid-price

class BlackScholesStrat(Strategy):
    def __init__(self, symbol: str, limit: int, strike: int, asset: str):
        super().__init__(symbol, limit)
        self.past_asset_data: List[float] = []
        self.asset = asset
        self.strike = strike
        self.max_sample_size = 100

    def load(self, data: List[float]) -> None:
        self.past_asset_data = data

    def save(self):
        return self.past_asset_data

    def stdnorm_cdf(self, x: float) -> float:
        return 0.5 * (1 + math.erf(x / np.sqrt(2)))
    
    def curr_price(self, state: TradingState) -> float:
        # Get the current price of the asset
        best_ask_asset = list(state.order_depths[self.asset].sell_orders.items())[0][0]
        best_bid_asset = list(state.order_depths[self.asset].buy_orders.items())[0][0]
        return (best_ask_asset + best_bid_asset) / 2
    
    def theoretical_price(self, state: TradingState) -> float:
        asset_prices = self.past_asset_data
        if len(asset_prices) < 3:
            volatility = 1.0
        else:
            asset_log_returns = [math.log(asset_prices[i + 1] / asset_prices[i]) 
                                 for i in range(len(asset_prices) - 1)]
            volatility = stdev(asset_log_returns)
        logger.print(f"Current asset volatility: {volatility}")
        S = self.curr_price(state)
        K = self.strike
        # T = 5 # 5 days from beginning of round 3 to expiry, 251 trading days in a year
        T = 5 - (state.timestamp // 1000000)
        r = 0  # risk-free interest rate, assumed to be 0
        d_plus : float = (math.log(S / K) + (r + volatility ** 2 / 2) * T) / (volatility * np.sqrt(T))
        d_minus : float = d_plus - volatility * np.sqrt(T)
        return S * self.stdnorm_cdf(d_plus) - K * math.exp(-r * T) * self.stdnorm_cdf(d_minus)

    def act(self, state: TradingState) -> None:
        order_depth = state.order_depths[self.symbol]
        fair_price = self.theoretical_price(state)
        try:
            best_ask = list(order_depth.sell_orders.items())[0][0]
            best_bid = list(order_depth.buy_orders.items())[0][0]
            real_price = (best_ask + best_bid) / 2
        except IndexError:
            real_price = fair_price
        logger.print(f"Current fair price: {fair_price}, current actual price: {real_price}")
        diff = fair_price - real_price

        min_diff = 0
        curr_pos = state.position.get(self.symbol, 0)
        if diff > min_diff: 
            # the option is underpriced, buy until  we reach the limit 
            # or until the current best ask exceeds the fair price
            for ask, vol in list(order_depth.sell_orders.items()):
                if self.limit - curr_pos <= -vol:
                    self.buy(ask, self.limit - curr_pos)
                    curr_pos = self.limit
                    break
                else:
                    self.buy(ask, -vol)
                    curr_pos -= vol

        elif diff < -min_diff:
            # the option is overpriced, sell until we reach the limit
            # or until the current best bid is less than the fair price
            for bid, vol in list(order_depth.buy_orders.items()):
                if self.limit + curr_pos <= vol:
                    self.sell(bid, self.limit + curr_pos)
                    curr_pos = -self.limit
                    break
                else:
                    self.sell(bid, vol)
                    curr_pos -= vol
        else:
            pass # option is fairly priced, do nothing

        # Update past asset data
        if len(self.past_asset_data) > self.max_sample_size:
            self.past_asset_data = self.past_asset_data[1:]
            self.past_asset_data.append(self.curr_price(state))
        else:
            self.past_asset_data.append(self.curr_price(state))
        return

class Volcanic9500Strat(BlackScholesStrat):
    def __init__(self, symbol: str, limit: int):
        super().__init__(symbol, limit, 9500, "VOLCANIC_ROCK")

class Volcanic9750Strat(BlackScholesStrat):
    def __init__(self, symbol: str, limit: int):
        super().__init__(symbol, limit, 9750, "VOLCANIC_ROCK")

class Volcanic10000Strat(BlackScholesStrat):
    def __init__(self, symbol: str, limit: int):
        super().__init__(symbol, limit, 10000, "VOLCANIC_ROCK")

class Volcanic10250Strat(BlackScholesStrat):
    def __init__(self, symbol: str, limit: int):
        super().__init__(symbol, limit, 10250, "VOLCANIC_ROCK")

class Volcanic10500Strat(BlackScholesStrat):
    def __init__(self, symbol: str, limit: int):
        super().__init__(symbol, limit, 10500, "VOLCANIC_ROCK")

class VolcanicRockStrategy(MACD):
    def __init__(self, symbol: str, limit: int):
        super().__init__(symbol, limit, 100)
        
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
            "PICNIC_BASKET2": 100,
            "VOLCANIC_ROCK": 400,
            "VOLCANIC_ROCK_VOUCHER_9500": 200,
            "VOLCANIC_ROCK_VOUCHER_9750" : 200,
            "VOLCANIC_ROCK_VOUCHER_10000" : 200,
            "VOLCANIC_ROCK_VOUCHER_10250" : 200,
            "VOLCANIC_ROCK_VOUCHER_10500" : 200
        }

        # Instantiate strategies for each symbol
        self.strategies = {
            symbol: strat(symbol, limits[symbol]) 
            for symbol, strat in {
                "VOLCANIC_ROCK_VOUCHER_9500": Volcanic9500Strat,
                "VOLCANIC_ROCK_VOUCHER_9750": Volcanic9750Strat,
                "VOLCANIC_ROCK_VOUCHER_10000": Volcanic10000Strat,
                "VOLCANIC_ROCK_VOUCHER_10250": Volcanic10250Strat,
                "VOLCANIC_ROCK_VOUCHER_10500": Volcanic10500Strat,
                "VOLCANIC_ROCK": VolcanicRockStrategy,
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
