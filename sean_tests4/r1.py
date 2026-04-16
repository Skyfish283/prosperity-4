import json
import math
import sys
from abc import abstractmethod
from collections import deque
from pathlib import Path
from statistics import pstdev
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

try:
    from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState

ASH_COATED_OSMIUM = "ASH_COATED_OSMIUM"
INTARIAN_PEPPER_ROOT = "INTARIAN_PEPPER_ROOT"

USE_LOGGER = True

# Best Osmium parameters from the staged sweep in osmium_mm_test.py.
DEFAULT_OSMIUM_STRATEGY_PARAMS: Dict[str, Any] = {
    "base_spread": 4.0,
    "inventory_skew_coeff": 5.0,
    "volatility_spread_coeff": 1.5,
    "volatility_lookback": 80,
    "fair_price_mid_coeff": 0.5,
}

# These are the tuned constants currently embedded in temp.py's pepper_root_strategy().
DEFAULT_PEPPER_STRATEGY_PARAMS: Dict[str, Any] = {
    "fair_price_base": 13_000.0,
    "fair_price_slope": 1_000.0,
    "close_start_timestamp": 999_000,
    "close_steps": 10,
    "close_step_size": 1_000,
    "close_passive_volume_per_step": 15,
    "close_passive_offset": 1,
    "close_aggression_ticks": 6,
    "close_front_level_size": 8,
    "close_extra_level_sizes": (6, 4),
    "normal_buy_levels": ((0, 4), (-1, 6), (-2, 8), (-3, 10), (-4, 5)),
    "normal_sell_levels": ((2, 4), (3, 6), (4, 8), (5, 10), (6, 5)),
}


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: Dict[Symbol, List[Order]], conversions: int, trader_data: str) -> None:
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

    def compress_state(self, state: TradingState, trader_data: str) -> List[Any]:
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

    def compress_listings(self, listings: Dict[Symbol, Listing]) -> List[List[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])
        return compressed

    def compress_order_depths(self, order_depths: Dict[Symbol, OrderDepth]) -> Dict[Symbol, List[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]
        return compressed

    def compress_trades(self, trades: Dict[Symbol, List[Trade]]) -> List[List[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [trade.symbol, trade.price, trade.quantity, trade.buyer, trade.seller, trade.timestamp]
                )
        return compressed

    def compress_observations(self, observations: Observation) -> List[Any]:
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

    def compress_orders(self, orders: Dict[Symbol, List[Order]]) -> List[List[Any]]:
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
    def __init__(self, symbol: Symbol, limit: int) -> None:
        self.symbol = symbol
        self.limit = limit

    @abstractmethod
    def act(self, state: TradingState) -> None:
        raise NotImplementedError()

    def run(self, state: TradingState) -> List[Order]:
        self.orders: List[Order] = []
        self.act(state)
        return self.orders

    def buy(self, price: int, quantity: int) -> None:
        self.orders.append(Order(self.symbol, price, quantity))

    def sell(self, price: int, quantity: int) -> None:
        self.orders.append(Order(self.symbol, price, -quantity))

    def save(self):
        return None

    def load(self, data) -> None:
        pass


class MarketMakingStrategy(Strategy):
    def __init__(
        self,
        symbol: Symbol,
        limit: int,
        base_spread: float = 2.0,
        volatility_lookback: int = 20,
        volatility_spread_coeff: float = 1.0,
        inventory_skew_coeff: float = 2.0,
        liquidation_window_size: int = 10,
    ) -> None:
        super().__init__(symbol, limit)
        self.window_size = liquidation_window_size
        self.window = deque(maxlen=self.window_size)
        self.base_spread = base_spread
        self.volatility_lookback = volatility_lookback
        self.volatility_spread_coeff = volatility_spread_coeff
        self.inventory_skew_coeff = inventory_skew_coeff
        self.mid_price_history: Deque[Tuple[int, float]] = deque(maxlen=self.volatility_lookback)

    @abstractmethod
    def get_true_value(self, state: TradingState) -> int:
        raise NotImplementedError()

    def get_observed_mid_price(
        self,
        true_value: float,
        buy_orders: List[Tuple[int, int]],
        sell_orders: List[Tuple[int, int]],
    ) -> float:
        if buy_orders and sell_orders:
            return (buy_orders[0][0] + sell_orders[0][0]) / 2
        if buy_orders:
            return float(buy_orders[0][0])
        if sell_orders:
            return float(sell_orders[0][0])
        return float(true_value)

    def record_mid_price(self, timestamp: int, mid_price: float) -> None:
        if self.mid_price_history and self.mid_price_history[-1][0] == timestamp:
            self.mid_price_history[-1] = (timestamp, mid_price)
            return
        self.mid_price_history.append((timestamp, mid_price))

    def get_current_volatility(self) -> float:
        if len(self.mid_price_history) < 2:
            return 0.0

        history = list(self.mid_price_history)
        price_changes = [
            curr_price - prev_price
            for (_, prev_price), (_, curr_price) in zip(history, history[1:])
        ]
        return float(pstdev(price_changes))

    def get_quotes(self, true_value: float, position: int, volatility: float) -> Tuple[int, int]:
        inventory_fraction = position / self.limit if self.limit else 0.0
        reservation_price = true_value - self.inventory_skew_coeff * inventory_fraction
        spread = max(1.0, self.base_spread + self.volatility_spread_coeff * volatility)

        bid_quote = math.floor(reservation_price - spread / 2)
        ask_quote = math.ceil(reservation_price + spread / 2)

        if bid_quote >= ask_quote:
            bid_quote = math.floor(reservation_price)
            ask_quote = bid_quote + 1

        return bid_quote, ask_quote

    def act(self, state: TradingState) -> None:
        true_value = float(self.get_true_value(state))

        order_depth = state.order_depths.get(self.symbol)
        if order_depth is None:
            return

        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True)
        sell_orders = sorted(order_depth.sell_orders.items())

        position = state.position.get(self.symbol, 0)
        to_buy = self.limit - position
        to_sell = self.limit + position

        observed_mid_price = self.get_observed_mid_price(true_value, buy_orders, sell_orders)
        self.record_mid_price(state.timestamp, observed_mid_price)
        current_volatility = self.get_current_volatility()
        bid_quote, ask_quote = self.get_quotes(true_value, position, current_volatility)

        self.window.append(abs(position) == self.limit)

        for price, volume in sell_orders:
            if to_buy <= 0 or price > bid_quote:
                break
            quantity = min(to_buy, -volume)
            if quantity > 0:
                self.buy(price, quantity)
                to_buy -= quantity

        if to_buy > 0:
            self.buy(bid_quote, to_buy)

        for price, volume in buy_orders:
            if to_sell <= 0 or price < ask_quote:
                break
            quantity = min(to_sell, volume)
            if quantity > 0:
                self.sell(price, quantity)
                to_sell -= quantity

        if to_sell > 0:
            self.sell(ask_quote, to_sell)

    def save(self):
        return {
            "window": list(self.window),
            "mid_price_history": list(self.mid_price_history),
        }

    def load(self, data) -> None:
        self.window = deque(maxlen=self.window_size)
        self.mid_price_history = deque(maxlen=self.volatility_lookback)

        if not data:
            return

        if isinstance(data, list):
            self.window.extend(data[-self.window_size:])
            return

        self.window.extend(data.get("window", [])[-self.window_size:])
        self.mid_price_history.extend(
            (int(timestamp), float(mid_price))
            for timestamp, mid_price in data.get("mid_price_history", [])[-self.volatility_lookback:]
        )


class OsmiumStrategy(MarketMakingStrategy):
    def __init__(
        self,
        symbol: Symbol,
        limit: int,
        fair_price_mid_coeff: float = 0.5,
        **kwargs,
    ) -> None:
        super().__init__(symbol, limit, **kwargs)
        self.fair_price_mid_coeff = fair_price_mid_coeff

    def get_true_value(self, state: TradingState) -> int:
        order_depth = state.order_depths.get(self.symbol)
        if order_depth is None:
            return 10_000

        best_bid = max(order_depth.buy_orders) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None

        if best_bid is not None and best_ask is not None:
            current_mid_price = (best_bid + best_ask) / 2
        elif best_bid is not None:
            current_mid_price = float(best_bid)
        elif best_ask is not None:
            current_mid_price = float(best_ask)
        else:
            current_mid_price = 10_000.0

        fair_price = 10_000 + self.fair_price_mid_coeff * (current_mid_price - 10_000)
        return round(fair_price)


class PepperStrategy(Strategy):
    def __init__(
        self,
        symbol: Symbol,
        limit: int,
        fair_price_base: float = 13_000.0,
        fair_price_slope: float = 1_000.0,
        close_start_timestamp: int = 999_000,
        close_steps: int = 10,
        close_step_size: int = 1_000,
        close_passive_volume_per_step: int = 15,
        close_passive_offset: int = 1,
        close_aggression_ticks: int = 6,
        close_front_level_size: int = 8,
        close_extra_level_sizes: Sequence[int] = (6, 4),
        normal_buy_levels: Sequence[Tuple[int, int]] = ((0, 4), (-1, 6), (-2, 8), (-3, 10), (-4, 5)),
        normal_sell_levels: Sequence[Tuple[int, int]] = ((2, 4), (3, 6), (4, 8), (5, 10), (6, 5)),
    ) -> None:
        super().__init__(symbol, limit)
        self.fair_price_base = fair_price_base
        self.fair_price_slope = fair_price_slope
        self.close_start_timestamp = close_start_timestamp
        self.close_steps = close_steps
        self.close_step_size = close_step_size
        self.close_passive_volume_per_step = close_passive_volume_per_step
        self.close_passive_offset = close_passive_offset
        self.close_aggression_ticks = close_aggression_ticks
        self.close_front_level_size = close_front_level_size
        self.close_extra_level_sizes = tuple(close_extra_level_sizes)
        self.normal_buy_levels = tuple(normal_buy_levels)
        self.normal_sell_levels = tuple(normal_sell_levels)

    def fair_price(self, state: TradingState) -> float:
        return self.fair_price_base + self.fair_price_slope * (state.timestamp / 1_000_000)

    def place_buy_ladder(self, levels: Sequence[Tuple[int, int]], remaining: int) -> None:
        for price, quantity in levels:
            actual = min(quantity, remaining)
            if actual > 0:
                self.buy(price, actual)
                remaining -= actual
            if remaining <= 0:
                return

    def place_sell_ladder(self, levels: Sequence[Tuple[int, int]], remaining: int) -> None:
        for price, quantity in levels:
            actual = min(quantity, remaining)
            if actual > 0:
                self.sell(price, actual)
                remaining -= actual
            if remaining <= 0:
                return

    def act(self, state: TradingState) -> None:
        fair = self.fair_price(state)
        position = state.position.get(self.symbol, 0)

        if state.timestamp >= self.close_start_timestamp:
            if position == 0:
                return

            end_timestamp = self.close_start_timestamp + self.close_steps * self.close_step_size
            steps_remaining = max(1.0, (end_timestamp - state.timestamp) / self.close_step_size)
            expected_passive_close = self.close_passive_volume_per_step * steps_remaining
            aggression = max(0.0, 1.0 - (steps_remaining / self.close_steps))

            if position > 0:
                base_ask = int(fair + self.close_passive_offset - aggression * self.close_aggression_ticks)
                must_close_now = max(0, int(position - expected_passive_close))
                close_sizes = (max(must_close_now, self.close_front_level_size), *self.close_extra_level_sizes)
                sell_levels = [(base_ask + offset, quantity) for offset, quantity in zip((0, 1, 2), close_sizes)]
                self.place_sell_ladder(sell_levels, position)
            else:
                base_bid = int(fair - self.close_passive_offset + aggression * self.close_aggression_ticks)
                must_close_now = max(0, int(-position - expected_passive_close))
                close_sizes = (max(must_close_now, self.close_front_level_size), *self.close_extra_level_sizes)
                buy_levels = [(base_bid + offset, quantity) for offset, quantity in zip((0, -1, -2), close_sizes)]
                self.place_buy_ladder(buy_levels, -position)
            return

        buy_capacity = self.limit - position
        buy_levels = [(int(fair) + offset, quantity) for offset, quantity in self.normal_buy_levels]
        self.place_buy_ladder(buy_levels, buy_capacity)

        sell_capacity = self.limit + position
        sell_levels = [(int(fair) + offset, quantity) for offset, quantity in self.normal_sell_levels]
        self.place_sell_ladder(sell_levels, sell_capacity)


class Trader:
    def __init__(self, strategy_params: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        limits = {
            ASH_COATED_OSMIUM: 80,
            INTARIAN_PEPPER_ROOT: 80,
        }
        strategy_params = strategy_params or {}
        default_strategy_params: Dict[str, Dict[str, Any]] = {
            ASH_COATED_OSMIUM: dict(DEFAULT_OSMIUM_STRATEGY_PARAMS),
            INTARIAN_PEPPER_ROOT: dict(DEFAULT_PEPPER_STRATEGY_PARAMS),
        }

        self.strategies = {
            symbol: strategy_class(
                symbol,
                limits[symbol],
                **{
                    **default_strategy_params.get(symbol, {}),
                    **strategy_params.get(symbol, {}),
                },
            )
            for symbol, strategy_class in {
                ASH_COATED_OSMIUM: OsmiumStrategy,
                INTARIAN_PEPPER_ROOT: PepperStrategy,
            }.items()
        }

    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        if USE_LOGGER:
            logger.print(state.position)

        old_trader_data = json.loads(state.traderData) if state.traderData != "" else {}
        new_trader_data: Dict[str, Any] = {}
        result: Dict[Symbol, List[Order]] = {}

        for symbol, strategy in self.strategies.items():
            if symbol in old_trader_data:
                strategy.load(old_trader_data.get(symbol, None))

            if symbol in state.order_depths:
                result[symbol] = strategy.run(state)

            new_trader_data[symbol] = strategy.save()

        trader_data = json.dumps(new_trader_data, separators=(",", ":"))
        conversions = 0

        if USE_LOGGER:
            logger.flush(state, result, conversions, trader_data)

        return result, conversions, trader_data
