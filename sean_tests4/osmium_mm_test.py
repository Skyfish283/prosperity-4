"""
Osmium market-making strategy plus a local grid-search harness.

Local tuning workflow:
- Run the staged sweep:
  `python sean_tests4/osmium_mm_test.py --days -2 -1 0 --top-n 5`
- Copy the winning values into `DEFAULT_OSMIUM_STRATEGY_PARAMS` below.
- Re-run a holdout backtest on unseen days before treating the tuned result as final.

Custom data example:
- `python sean_tests4/osmium_mm_test.py --data /path/to/prosperity4bt/resources --days -2 -1 0`
"""

import argparse
import json
import sys
from abc import abstractmethod
from collections import defaultdict, deque
from itertools import product
import math
from pathlib import Path
from statistics import pstdev
from typing import *

try:
    from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState

ASH_COATED_OSMIUM = "ASH_COATED_OSMIUM"
INTARIAN_PEPPER_ROOT = "INTARIAN_PEPPER_ROOT"

# Edit these values after running the local grid search.
DEFAULT_OSMIUM_STRATEGY_PARAMS: Dict[str, Any] = {
    "base_spread": 4.0,
    "inventory_skew_coeff": 5.0,
    "volatility_spread_coeff": 1.5,
    "volatility_lookback": 80,
    "fair_price_mid_coeff": 0.5,
}

# Local grid-search defaults and search ranges.
GRID_SEARCH_DEFAULT_ROUND = 1
GRID_SEARCH_DEFAULT_DAYS = (-2, -1, 0)
GRID_SEARCH_DEFAULT_TOP_N = 5
GRID_SEARCH_DEFAULT_MATCH_TRADES = "all"
GRID_SEARCH_BASE_SPREADS = [1.0, 2.0, 3.0, 4.0]
GRID_SEARCH_INVENTORY_SKEWS = [0.5, 1.0, 2.0, 3.0, 5.0]
GRID_SEARCH_FAIR_PRICE_COEFFS = [0.0, 0.25, 0.5, 0.75, 1.0]
GRID_SEARCH_VOLATILITY_COEFFS = [0.0, 0.5, 1.0, 1.5, 2.5]
GRID_SEARCH_VOLATILITY_LOOKBACKS = [10, 20, 40, 80]

USE_LOGGER = True

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
        self.window = deque(maxlen=self.window_size)  # Tracks recent extreme positions
        self.base_spread = base_spread
        self.volatility_lookback = volatility_lookback
        self.volatility_spread_coeff = volatility_spread_coeff
        self.inventory_skew_coeff = inventory_skew_coeff
        # Persist a rolling price path so volatility can be computed across timestamps.
        self.mid_price_history: Deque[Tuple[int, float]] = deque(maxlen=self.volatility_lookback)

    @abstractmethod
    def get_true_value(self, state: TradingState) -> int:
        # Subclasses define how to compute the asset's true value
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

    def get_quotes(
        self,
        true_value: float,
        position: int,
        volatility: float,
    ) -> Tuple[int, int]:
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
        true_value = float(self.get_true_value(state))  # Estimated fair price of the asset

        order_depth = state.order_depths.get(self.symbol)
        if order_depth is None:
            return

        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True)  # Highest bid first
        sell_orders = sorted(order_depth.sell_orders.items())              # Lowest ask first

        position = state.position.get(self.symbol, 0)
        to_buy = self.limit - position   # Remaining capacity to buy
        to_sell = self.limit + position  # Remaining capacity to sell

        observed_mid_price = self.get_observed_mid_price(true_value, buy_orders, sell_orders)
        self.record_mid_price(state.timestamp, observed_mid_price)
        current_volatility = self.get_current_volatility()
        bid_quote, ask_quote = self.get_quotes(true_value, position, current_volatility)

        self.window.append(abs(position) == self.limit)

        # Take any ask already priced through our bid quote.
        for price, volume in sell_orders:
            if to_buy <= 0 or price > bid_quote:
                break
            quantity = min(to_buy, -volume)
            if quantity > 0:
                self.buy(price, quantity)
                to_buy -= quantity

        # Post the residual bid at our computed quote.
        if to_buy > 0:
            self.buy(bid_quote, to_buy)

        # Take any bid already priced through our ask quote.
        for price, volume in buy_orders:
            if to_sell <= 0 or price < ask_quote:
                break
            quantity = min(to_sell, volume)
            if quantity > 0:
                self.sell(price, quantity)
                to_sell -= quantity

        # Post the residual ask at our computed quote.
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

        # Backward compatibility with the previous save format.
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

class Trader:
    def __init__(self, strategy_params: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        limits = {
            ASH_COATED_OSMIUM: 80,
            INTARIAN_PEPPER_ROOT: 80,
        }
        strategy_params = strategy_params or {}
        default_strategy_params: Dict[str, Dict[str, Any]] = {
            ASH_COATED_OSMIUM: dict(DEFAULT_OSMIUM_STRATEGY_PARAMS),
        }

        # Instantiate strategies for each symbol
        self.strategies = {
            symbol: strat(
                symbol,
                limits[symbol],
                **{
                    **default_strategy_params.get(symbol, {}),
                    **strategy_params.get(symbol, {}),
                },
            )
            for symbol, strat in {
                ASH_COATED_OSMIUM: OsmiumStrategy,
            }.items()
        }

    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        if USE_LOGGER:
            logger.print(state.position)  # Log current positions

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

        conversions = 0 # placeholder for conversion tracking

        if USE_LOGGER:
            logger.flush(state, result, conversions, trader_data)  # Flush logs to output

        return result, conversions, trader_data


def _load_backtester_modules():
    try:
        from prosperity4bt.file_reader import FileSystemReader, PackageResourcesReader
        from prosperity4bt.metrics import risk_metrics_full_period
        from prosperity4bt.models import TradeMatchingMode
        from prosperity4bt.runner import run_backtest
    except ImportError:
        from backtester.prosperity4bt.file_reader import FileSystemReader, PackageResourcesReader
        from backtester.prosperity4bt.metrics import risk_metrics_full_period
        from backtester.prosperity4bt.models import TradeMatchingMode
        from backtester.prosperity4bt.runner import run_backtest

    return FileSystemReader, PackageResourcesReader, risk_metrics_full_period, TradeMatchingMode, run_backtest


def _inventory_metrics(results, symbol: Symbol, limit: int) -> Dict[str, float]:
    pos_samples: List[int] = []
    near_limit_count = 0
    total_samples = 0
    turnover = 0
    trade_count = 0

    for result in results:
        net_by_timestamp: DefaultDict[int, int] = defaultdict(int)
        for trade_row in result.trades:
            trade = trade_row.trade
            if trade.symbol != symbol:
                continue

            trade_count += 1
            turnover += trade.quantity

            if trade.buyer == "SUBMISSION":
                net_by_timestamp[trade.timestamp] += trade.quantity
            elif trade.seller == "SUBMISSION":
                net_by_timestamp[trade.timestamp] -= trade.quantity

        timestamps = sorted(
            row.timestamp
            for row in result.activity_logs
            if row.columns[2] == symbol
        )
        position = 0
        for timestamp in timestamps:
            abs_position = abs(position)
            pos_samples.append(abs_position)
            total_samples += 1
            if abs_position >= 0.75 * limit:
                near_limit_count += 1
            position += net_by_timestamp.get(timestamp, 0)

    mean_abs_position = sum(pos_samples) / len(pos_samples) if pos_samples else 0.0
    max_abs_position = max(pos_samples) if pos_samples else 0.0
    near_limit_fraction = near_limit_count / total_samples if total_samples else 0.0
    return {
        "turnover": float(turnover),
        "trade_count": float(trade_count),
        "mean_abs_position": float(mean_abs_position),
        "max_abs_position": float(max_abs_position),
        "near_limit_fraction": float(near_limit_fraction),
    }


def _evaluate_strategy_params(
    reader,
    round_num: int,
    days: Sequence[int],
    trade_matching_mode: str,
    symbol: Symbol,
    limit: int,
    strategy_params: Dict[str, Any],
) -> Dict[str, Any]:
    global USE_LOGGER

    _, _, risk_metrics_full_period, TradeMatchingMode, run_backtest = _load_backtester_modules()
    old_use_logger = USE_LOGGER
    USE_LOGGER = False
    try:
        results = []
        for day in days:
            trader = Trader(strategy_params={symbol: dict(strategy_params)})
            results.append(
                run_backtest(
                    trader,
                    reader,
                    round_num,
                    day,
                    False,
                    getattr(TradeMatchingMode, trade_matching_mode),
                    True,
                    False,
                )
            )
    finally:
        USE_LOGGER = old_use_logger

    risk = risk_metrics_full_period(results)
    inventory = _inventory_metrics(results, symbol, limit)
    turnover = inventory["turnover"]
    pnl_per_turnover = risk.final_pnl / turnover if turnover else float("nan")
    return {
        "params": dict(strategy_params),
        "final_pnl": risk.final_pnl,
        "max_drawdown_abs": risk.max_drawdown_abs,
        "calmar_ratio": risk.calmar_ratio,
        "annualized_sharpe": risk.annualized_sharpe,
        "turnover": inventory["turnover"],
        "trade_count": inventory["trade_count"],
        "mean_abs_position": inventory["mean_abs_position"],
        "max_abs_position": inventory["max_abs_position"],
        "near_limit_fraction": inventory["near_limit_fraction"],
        "pnl_per_turnover": pnl_per_turnover,
    }


def _print_grid_stage(stage_name: str, rows: Sequence[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: row["final_pnl"], reverse=True)
    print(f"=== {stage_name} ===")
    for row in ranked[:top_n]:
        summary = {
            "params": row["params"],
            "final_pnl": round(row["final_pnl"], 1),
            "max_drawdown_abs": round(row["max_drawdown_abs"], 1),
            "calmar_ratio": round(row["calmar_ratio"], 5) if row["calmar_ratio"] == row["calmar_ratio"] else None,
            "turnover": int(row["turnover"]),
            "trade_count": int(row["trade_count"]),
            "mean_abs_position": round(row["mean_abs_position"], 2),
            "near_limit_fraction": round(row["near_limit_fraction"], 4),
            "pnl_per_turnover": round(row["pnl_per_turnover"], 5) if row["pnl_per_turnover"] == row["pnl_per_turnover"] else None,
        }
        print(json.dumps(summary, sort_keys=True))
    print()
    return ranked


def run_local_grid_search(
    round_num: int = GRID_SEARCH_DEFAULT_ROUND,
    days: Sequence[int] = GRID_SEARCH_DEFAULT_DAYS,
    top_n: int = GRID_SEARCH_DEFAULT_TOP_N,
    data_path: Optional[str] = None,
    trade_matching_mode: str = GRID_SEARCH_DEFAULT_MATCH_TRADES,
) -> Dict[str, Any]:
    FileSystemReader, PackageResourcesReader, _, _, _ = _load_backtester_modules()

    if data_path is None:
        reader = PackageResourcesReader()
    else:
        reader = FileSystemReader(Path(data_path).resolve())

    symbol = ASH_COATED_OSMIUM
    limit = 80

    stage1 = []
    for base_spread, inventory_skew_coeff, fair_price_mid_coeff in product(
        GRID_SEARCH_BASE_SPREADS,
        GRID_SEARCH_INVENTORY_SKEWS,
        GRID_SEARCH_FAIR_PRICE_COEFFS,
    ):
        stage1.append(
            _evaluate_strategy_params(
                reader=reader,
                round_num=round_num,
                days=days,
                trade_matching_mode=trade_matching_mode,
                symbol=symbol,
                limit=limit,
                strategy_params={
                    "base_spread": base_spread,
                    "inventory_skew_coeff": inventory_skew_coeff,
                    "volatility_spread_coeff": 0.0,
                    "volatility_lookback": 20,
                    "fair_price_mid_coeff": fair_price_mid_coeff,
                },
            )
        )
    ranked_stage1 = _print_grid_stage(
        "Stage 1: base spread, inventory skew, fair-price coefficient (volatility off)",
        stage1,
        top_n,
    )
    best_params = dict(ranked_stage1[0]["params"])

    stage2 = []
    for volatility_spread_coeff in GRID_SEARCH_VOLATILITY_COEFFS:
        params = dict(best_params)
        params["volatility_spread_coeff"] = volatility_spread_coeff
        stage2.append(
            _evaluate_strategy_params(
                reader=reader,
                round_num=round_num,
                days=days,
                trade_matching_mode=trade_matching_mode,
                symbol=symbol,
                limit=limit,
                strategy_params=params,
            )
        )
    ranked_stage2 = _print_grid_stage("Stage 2: volatility spread coefficient", stage2, top_n)
    best_params = dict(ranked_stage2[0]["params"])

    stage3 = []
    for volatility_lookback in GRID_SEARCH_VOLATILITY_LOOKBACKS:
        params = dict(best_params)
        params["volatility_lookback"] = volatility_lookback
        stage3.append(
            _evaluate_strategy_params(
                reader=reader,
                round_num=round_num,
                days=days,
                trade_matching_mode=trade_matching_mode,
                symbol=symbol,
                limit=limit,
                strategy_params=params,
            )
        )
    ranked_stage3 = _print_grid_stage("Stage 3: volatility lookback", stage3, top_n)
    best_params = dict(ranked_stage3[0]["params"])

    stage4 = []
    for fair_price_mid_coeff in GRID_SEARCH_FAIR_PRICE_COEFFS:
        params = dict(best_params)
        params["fair_price_mid_coeff"] = fair_price_mid_coeff
        stage4.append(
            _evaluate_strategy_params(
                reader=reader,
                round_num=round_num,
                days=days,
                trade_matching_mode=trade_matching_mode,
                symbol=symbol,
                limit=limit,
                strategy_params=params,
            )
        )
    ranked_stage4 = _print_grid_stage("Stage 4: fair-price coefficient revisit", stage4, top_n)
    best_result = ranked_stage4[0]

    print("=== FINAL BEST CONFIG ===")
    print(json.dumps(best_result, sort_keys=True, default=str))

    return {
        "stage1": ranked_stage1,
        "stage2": ranked_stage2,
        "stage3": ranked_stage3,
        "stage4": ranked_stage4,
        "best": best_result,
    }


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local staged grid search for OsmiumStrategy.")
    parser.add_argument(
        "--round",
        dest="round_num",
        type=int,
        default=GRID_SEARCH_DEFAULT_ROUND,
        help="Backtest round number.",
    )
    parser.add_argument(
        "--days",
        type=int,
        nargs="+",
        default=list(GRID_SEARCH_DEFAULT_DAYS),
        help="Round days to include in the sweep.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=GRID_SEARCH_DEFAULT_TOP_N,
        help="Number of top configurations to print per stage.",
    )
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="Optional path to a custom prosperity4bt-style data directory.",
    )
    parser.add_argument(
        "--match-trades",
        choices=["all", "worse", "none"],
        default=GRID_SEARCH_DEFAULT_MATCH_TRADES,
        help="Trade matching mode passed to the backtester.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_cli_args()
    run_local_grid_search(
        round_num=args.round_num,
        days=args.days,
        top_n=args.top_n,
        data_path=args.data,
        trade_matching_mode=args.match_trades,
    )
