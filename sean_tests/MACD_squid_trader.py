from datamodel import *
from typing import *
import string
from statistics import *
import math
import jsonpickle
import pandas as pd
import numpy as np

Product = str
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

class Trader:

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
    
    def run(self, state: TradingState):
        # print("traderData: " + state.traderData)
        # print("Observations: " + str(state.observations))

        tempdata: Dict[Product, List[float]] = {}
        if state.traderData not in [None, "null", ""]:
            tempdata : Dict[Product, List[float]] = jsonpickle.decode(state.traderData)
        else:
            tempdata["SQUID_INK"] = []
        result = {}
        orders: List[Order] = []

        order_depth = state.order_depths["SQUID_INK"]

        MACD_signals = self.MACD(state, tempdata.get("SQUID_INK",[]))
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
        if len(tempdata.get(product, [])) > max_sample_size:
            tempdata[product] = tempdata[product][1:]
            tempdata[product].append((best_ask + best_bid) / 2)
        else:
            tempdata[product].append((best_ask + best_bid) / 2)

        result[product] = orders
        traderData = jsonpickle.encode(tempdata)
        conversions = None
        logger.flush(state, { "SQUID_INK": orders }, conversions, traderData)
        logger.print(MACD_signals, ideal_pos, pos_diff)
        return result, conversions, traderData
        
