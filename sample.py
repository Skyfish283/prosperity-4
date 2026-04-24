import json
import math
from typing import Any, Optional

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


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
                    [trade.symbol, trade.price, trade.quantity, trade.buyer, trade.seller, trade.timestamp]
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
        lo, hi = 0, min(len(value), max_length)
        out = ""

        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = value[:mid]
            if len(candidate) < len(value):
                candidate += "..."
            encoded_candidate = json.dumps(candidate)
            if len(encoded_candidate) <= max_length:
                out = candidate
                lo = mid + 1
            else:
                hi = mid - 1

        return out


logger = Logger()


class Trader:
    DELTA1_PRODUCTS = ("HYDROGEL_PACK", "VELVETFRUIT_EXTRACT")
    OPTION_STRIKES = {
        "VEV_4000": 4000,
        "VEV_4500": 4500,
        "VEV_5000": 5000,
        "VEV_5100": 5100,
        "VEV_5200": 5200,
        "VEV_5300": 5300,
        "VEV_5400": 5400,
        "VEV_5500": 5500,
        "VEV_6000": 6000,
        "VEV_6500": 6500,
    }
    POSITION_LIMITS = {
        "HYDROGEL_PACK": 200,
        "VELVETFRUIT_EXTRACT": 200,
        **{symbol: 300 for symbol in OPTION_STRIKES},
    }
    TTE_YEARS = 5.0 / 365.0
    DEFAULT_SIGMA = 0.33

    def _best_bid_ask(self, order_depth: OrderDepth) -> tuple[Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None
        return best_bid, best_ask

    def _mid_price(self, order_depth: OrderDepth) -> Optional[float]:
        best_bid, best_ask = self._best_bid_ask(order_depth)
        if best_bid is None and best_ask is None:
            return None
        if best_bid is None:
            return float(best_ask)
        if best_ask is None:
            return float(best_bid)
        return (best_bid + best_ask) / 2.0

    def _norm_cdf(self, x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def _call_price(self, spot: float, strike: float, tte: float, sigma: float) -> float:
        if tte <= 0.0:
            return max(0.0, spot - strike)
        sigma = max(1e-4, sigma)
        sqrt_t = math.sqrt(tte)
        vol_term = sigma * sqrt_t
        d1 = (math.log(max(spot, 1e-6) / strike) + 0.5 * sigma * sigma * tte) / vol_term
        d2 = d1 - vol_term
        return max(0.0, spot * self._norm_cdf(d1) - strike * self._norm_cdf(d2))

    def _call_delta(self, spot: float, strike: float, tte: float, sigma: float) -> float:
        if tte <= 0.0:
            return 1.0 if spot > strike else 0.0
        sigma = max(1e-4, sigma)
        d1 = (math.log(max(spot, 1e-6) / strike) + 0.5 * sigma * sigma * tte) / (sigma * math.sqrt(tte))
        return self._norm_cdf(d1)

    def _implied_vol_from_call(self, target: float, spot: float, strike: float, tte: float) -> float:
        intrinsic = max(0.0, spot - strike)
        if target <= intrinsic + 0.01:
            return 0.05
        lo, hi = 0.01, 3.0
        for _ in range(28):
            mid = 0.5 * (lo + hi)
            px = self._call_price(spot, strike, tte, mid)
            if px < target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def _allowable_buy(self, product: Symbol, position: int) -> int:
        return max(0, self.POSITION_LIMITS[product] - position)

    def _allowable_sell(self, product: Symbol, position: int) -> int:
        return max(0, self.POSITION_LIMITS[product] + position)

    def _place_taking_orders(
        self,
        product: Symbol,
        order_depth: OrderDepth,
        fair_value: float,
        position: int,
        edge: float,
    ) -> tuple[list[Order], int]:
        orders: list[Order] = []

        buy_remaining = self._allowable_buy(product, position)
        for ask_price in sorted(order_depth.sell_orders):
            if ask_price > fair_value - edge or buy_remaining <= 0:
                break
            available = -order_depth.sell_orders[ask_price]
            qty = min(available, buy_remaining)
            if qty > 0:
                orders.append(Order(product, ask_price, qty))
                position += qty
                buy_remaining -= qty

        sell_remaining = self._allowable_sell(product, position)
        for bid_price in sorted(order_depth.buy_orders, reverse=True):
            if bid_price < fair_value + edge or sell_remaining <= 0:
                break
            available = order_depth.buy_orders[bid_price]
            qty = min(available, sell_remaining)
            if qty > 0:
                orders.append(Order(product, bid_price, -qty))
                position -= qty
                sell_remaining -= qty

        return orders, position

    def _place_quote_pair(
        self,
        product: Symbol,
        order_depth: OrderDepth,
        fair_value: float,
        position: int,
        width: int,
        clip: int,
    ) -> list[Order]:
        orders: list[Order] = []
        best_bid, best_ask = self._best_bid_ask(order_depth)
        if best_bid is None or best_ask is None:
            return orders

        limit = self.POSITION_LIMITS[product]
        buy_capacity = self._allowable_buy(product, position)
        sell_capacity = self._allowable_sell(product, position)
        if buy_capacity <= 0 and sell_capacity <= 0:
            return orders

        inv_skew = position / max(1, limit)
        buy_quote = min(best_bid + 1, int(fair_value - width - inv_skew * 2.0))
        sell_quote = max(best_ask - 1, int(fair_value + width - inv_skew * 2.0))
        if buy_quote >= sell_quote:
            buy_quote, sell_quote = best_bid, best_ask

        buy_size = min(buy_capacity, clip)
        sell_size = min(sell_capacity, clip)
        if buy_size > 0:
            orders.append(Order(product, buy_quote, buy_size))
        if sell_size > 0:
            orders.append(Order(product, sell_quote, -sell_size))
        return orders

    def run(self, state: TradingState):
        persisted: dict[str, float] = {}
        if state.traderData:
            try:
                loaded = json.loads(state.traderData)
                if isinstance(loaded, dict):
                    persisted = loaded
            except Exception:
                persisted = {}

        result: dict[Symbol, list[Order]] = {}
        mids: dict[str, float] = {}
        for product, depth in state.order_depths.items():
            mid = self._mid_price(depth)
            if mid is not None:
                mids[product] = mid

        # Delta-1 fair values.
        hydrogel_mid = mids.get("HYDROGEL_PACK", persisted.get("hydrogel_ewma", 10_000.0))
        hydrogel_fair = 0.9 * persisted.get("hydrogel_ewma", hydrogel_mid) + 0.1 * hydrogel_mid
        velvet_mid = mids.get("VELVETFRUIT_EXTRACT", persisted.get("velvet_ewma", 5_250.0))
        velvet_fair = 0.85 * persisted.get("velvet_ewma", velvet_mid) + 0.15 * velvet_mid

        # Estimate implied vol from near-the-money option and smooth it.
        sigma = persisted.get("sigma", self.DEFAULT_SIGMA)
        atm_symbol = "VEV_5300"
        if atm_symbol in mids:
            sample_sigma = self._implied_vol_from_call(mids[atm_symbol], velvet_fair, 5300.0, self.TTE_YEARS)
            sigma = 0.8 * sigma + 0.2 * sample_sigma

        # Trade delta-1 products first.
        for product, fair_value, edge, width, clip in (
            ("HYDROGEL_PACK", hydrogel_fair, 1.5, 2, 30),
            ("VELVETFRUIT_EXTRACT", velvet_fair, 1.0, 1, 25),
        ):
            depth = state.order_depths.get(product)
            if depth is None:
                continue
            pos = state.position.get(product, 0)
            orders, post_take_pos = self._place_taking_orders(product, depth, fair_value, pos, edge)
            orders.extend(self._place_quote_pair(product, depth, fair_value, post_take_pos, width, clip))
            result[product] = orders

        # Voucher strategy: model-value taking + passive quotes.
        total_option_delta = 0.0
        for option_symbol, strike in self.OPTION_STRIKES.items():
            depth = state.order_depths.get(option_symbol)
            if depth is None:
                continue
            pos = state.position.get(option_symbol, 0)
            total_option_delta += pos * self._call_delta(velvet_fair, float(strike), self.TTE_YEARS, sigma)

            theo = self._call_price(velvet_fair, float(strike), self.TTE_YEARS, sigma)
            market_mid = mids.get(option_symbol, theo)
            fair = 0.6 * theo + 0.4 * market_mid

            edge = 1.0 if strike <= 5200 else 0.5
            orders, post_take_pos = self._place_taking_orders(option_symbol, depth, fair, pos, edge)
            quote_width = 2 if strike <= 5200 else 1
            clip = 45 if strike <= 5200 else 35
            orders.extend(self._place_quote_pair(option_symbol, depth, fair, post_take_pos, quote_width, clip))
            result[option_symbol] = orders

        # Simple soft hedge: skew VELVET fair against aggregate option delta.
        hedge_product = "VELVETFRUIT_EXTRACT"
        if hedge_product in state.order_depths:
            hedge_depth = state.order_depths[hedge_product]
            hedge_pos = state.position.get(hedge_product, 0)
            desired_hedge = -int(total_option_delta)
            gap = desired_hedge - hedge_pos
            if gap != 0:
                extra: list[Order] = result.get(hedge_product, [])
                best_bid, best_ask = self._best_bid_ask(hedge_depth)
                if best_bid is not None and best_ask is not None:
                    if gap > 0:
                        buy_qty = min(gap, self._allowable_buy(hedge_product, hedge_pos), 35)
                        if buy_qty > 0:
                            extra.append(Order(hedge_product, best_ask, buy_qty))
                    else:
                        sell_qty = min(-gap, self._allowable_sell(hedge_product, hedge_pos), 35)
                        if sell_qty > 0:
                            extra.append(Order(hedge_product, best_bid, -sell_qty))
                result[hedge_product] = extra

        logger.print(
            f"hydrogel_fair={hydrogel_fair:.2f} velvet_fair={velvet_fair:.2f} "
            f"sigma={sigma:.3f} opt_delta={total_option_delta:.1f}"
        )

        trader_data = json.dumps(
            {"hydrogel_ewma": hydrogel_fair, "velvet_ewma": velvet_fair, "sigma": sigma},
            separators=(",", ":"),
        )
        conversions = 0

        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data
