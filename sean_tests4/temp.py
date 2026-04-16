import json
import itertools
import subprocess
import re
import textwrap
from pathlib import Path
from typing import Any, List

try:
    from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
except ImportError:
    Listing = Observation = Order = OrderDepth = ProsperityEncoder = Symbol = Trade = TradingState = object

HYPERPARAMS = {
    "base_edge": [i for i in range(5, 10)],
    "k": [i / 100 for i in range(11)],
    "weight": [i / 10 for i in range(11)],
}


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
    def __init__(self):
        self.limits = {
            'INTARIAN_PEPPER_ROOT': 80,
            'ASH_COATED_OSMIUM': 80
        }

    def bid(self):
        return 15
    

    def pepper_root_strategy(self, state: TradingState) -> List[Order]:
        fair = 13000 + 1000 * (state.timestamp / 1000000)
        pos = state.position.get('INTARIAN_PEPPER_ROOT', 0)
        orders = []
    
        # --- CLOSING STRATEGY ---
        if state.timestamp >= 999000:
            if pos == 0:
                return orders
    
            end_timestamp = 999000 + 10 * 1000
            steps_remaining = max(1, (end_timestamp - state.timestamp) / 1000)
    
            # ~15 passive fills per step (half of ~30 daily volume)
            expected_passive_close = 15 * steps_remaining
    
            # Aggression ramps from 0 (start of close) to 1 (final step)
            aggression = max(0.0, 1.0 - (steps_remaining / 10))
    
            if pos > 0:  # long — need to sell
                # Passive: fair+1 (break-even on drift), aggressive: fair-5 (cross spread)
                base_ask = int(fair + 1 - aggression * 6)
                must_close_now = max(0, int(pos - expected_passive_close))
    
                sell_levels = [
                    (base_ask,     max(must_close_now, 8)),
                    (base_ask + 1, 6),
                    (base_ask + 2, 4),
                ]
                remaining = pos
                for price, qty in sell_levels:
                    actual = min(qty, remaining)
                    if actual > 0:
                        orders.append(Order('INTARIAN_PEPPER_ROOT', price, -actual))
                        remaining -= actual
                    if remaining <= 0:
                        break
    
            elif pos < 0:  # short — need to buy
                # Passive: fair-1 (break-even on drift), aggressive: fair+5 (cross spread)
                base_bid = int(fair - 1 + aggression * 6)
                must_close_now = max(0, int(-pos - expected_passive_close))
    
                buy_levels = [
                    (base_bid,     max(must_close_now, 8)),
                    (base_bid - 1, 6),
                    (base_bid - 2, 4),
                ]
                remaining = -pos
                for price, qty in buy_levels:
                    actual = min(qty, remaining)
                    if actual > 0:
                        orders.append(Order('INTARIAN_PEPPER_ROOT', price, actual))
                        remaining -= actual
                    if remaining <= 0:
                        break
    
            return orders
    
        # --- BUY SIDE ---
        buy_capacity = 80 - pos
        buy_levels = [
            (int(fair),     4),
            (int(fair) - 1, 6),
            (int(fair) - 2, 8),
            (int(fair) - 3, 10),
            (int(fair) - 4, 5),
        ]
        remaining = buy_capacity
        for price, qty in buy_levels:
            actual = min(qty, remaining)
            if actual > 0:
                orders.append(Order('INTARIAN_PEPPER_ROOT', price, actual))
                remaining -= actual
            if remaining <= 0:
                break
    
        # --- SELL SIDE ---
        sell_capacity = pos + 80
        sell_levels = [
            (int(fair) + 2, 4),
            (int(fair) + 3, 6),
            (int(fair) + 4, 8),
            (int(fair) + 5, 10),
            (int(fair) + 6, 5),
        ]
        remaining = sell_capacity
        for price, qty in sell_levels:
            actual = min(qty, remaining)
            if actual > 0:
                orders.append(Order('INTARIAN_PEPPER_ROOT', price, -actual))
                remaining -= actual
            if remaining <= 0:
                break
    
        return orders
    
    def osmium_strategy(self, state):
        product = "ASH_COATED_OSMIUM"
        limit = 80
        
       
        if product in state.order_depths:
            depth = state.order_depths[product]
            orders: List[Order] = []
            current_pos = state.position.get(product, 0)
 
            if depth.buy_orders and depth.sell_orders:
                best_bid = max(depth.buy_orders.keys())
                best_ask = min(depth.sell_orders.keys())
                mid = (best_bid + best_ask) / 2
                # different calculations of fair
                fair_1 = 10000
                fair_2 = mid
                weighting_for_fair = 0.8
                fair_3 = (weighting_for_fair * mid) + (1-weighting_for_fair) * 10000
                base_edge = 1
                # edge = base_edge + k*pos
                k = 0.1
 
                # --- MARKET MAKING LOGIC ---
 
                # 1. SELL SIDE
                if current_pos > -limit:
                    sell_price = round(fair_1 + base_edge - (k*current_pos))
                    sell_vol = -limit - current_pos
                    orders.append(Order(product, sell_price, sell_vol))
 
                # 2. BUY SIDE
                if current_pos < limit:
                    buy_price = round(fair_1 - base_edge - (k*current_pos))
 
                    buy_vol = limit - current_pos
                    orders.append(Order(product, buy_price, buy_vol))
 
        return orders
    
        
    def grid_search_pepper_root_strategy(self, round_day: str = "1"):
        PEPPER_GRID = {
            "X": list(range(0, 6)),        # buy offset from fair: -5 to +5
            "Y": list(range(0, 11)),         # sell offset from fair: 0 to +10
        }

        TRADER_TEMPLATE = textwrap.dedent("""\
            from datamodel import TradingState, Order
            from typing import List

            X = {X}
            Y = {Y}

            class Trader:
                def run(self, state: TradingState):
                    product = "INTARIAN_PEPPER_ROOT"
                    MAX_POS = 80
                    fair = 12000 + 1000 * (state.timestamp / 1000000)
                    pos = state.position.get(product, 0)
                    orders: List[Order] = []

                    if state.timestamp >= 999000:
                        if pos > 0:
                            orders.append(Order(product, int(fair) - 2, -pos))
                        elif pos < 0:
                            orders.append(Order(product, int(fair) + 2, -pos))
                        return {{product: orders}}, 0, ""

                    buy_capacity = max(0, MAX_POS - pos)
                    if buy_capacity > 0:
                        orders.append(Order(product, int(fair + X), buy_capacity))

                    sell_capacity = max(0, MAX_POS + pos)
                    if sell_capacity > 0:
                        orders.append(Order(product, int(fair + Y), -sell_capacity))

                    return {{product: orders}}, 0, ""
        """)

        tmp_file = Path("_grid_tmp_trader.py")
        keys = list(PEPPER_GRID.keys())
        combos = list(itertools.product(*PEPPER_GRID.values()))
        results = []

        print(f"Pepper root grid search: {len(combos)} combos on {round_day}\n")

        for combo in combos:
            params = dict(zip(keys, combo))
            tmp_file.write_text(TRADER_TEMPLATE.format(**params))

            proc = subprocess.run(
                ["uv", "run", "prosperity4btest", str(tmp_file), round_day, "--no-out"],
                capture_output=True, text=True,
            )
            output = proc.stdout + proc.stderr
            match = re.search(r"INTARIAN_PEPPER_ROOT:\s*([\d,\-]+)", output)
            if not match:
                match = re.search(r"Total profit:\s*([\d,\-]+)", output)
            pnl = float(match.group(1).replace(",", "")) if match else float("nan")

            results.append((pnl, params))
            print(f"  X={params['X']:>+3}  Y={params['Y']:>+3}  pnl={pnl:>12,.0f}")

        tmp_file.unlink(missing_ok=True)

        results.sort(key=lambda x: x[0], reverse=True)
        print("\n=== Top 5 combos ===")
        for pnl, params in results[:5]:
            print(f"  pnl={pnl:>12,.0f}  {params}")

        return results

    def grid_search_osmium_strategy(self, round_day: str = "1-0"):
        TRADER_TEMPLATE = textwrap.dedent("""\
            from datamodel import TradingState, Order
            from typing import List

            BASE_EDGE = {base_edge}
            K         = {k}
            WEIGHT    = {weight}

            class Trader:
                def run(self, state: TradingState):
                    product = "ASH_COATED_OSMIUM"
                    limit   = 80
                    orders: List[Order] = []

                    if product not in state.order_depths:
                        return {{product: orders}}, 0, ""

                    depth       = state.order_depths[product]
                    current_pos = state.position.get(product, 0)

                    if not (depth.buy_orders and depth.sell_orders):
                        return {{product: orders}}, 0, ""

                    best_bid = max(depth.buy_orders.keys())
                    best_ask = min(depth.sell_orders.keys())
                    mid      = (best_bid + best_ask) / 2

                    fair = WEIGHT * mid + (1 - WEIGHT) * 10000

                    if current_pos > -limit:
                        sell_price = round(fair + BASE_EDGE - K * current_pos)
                        orders.append(Order(product, sell_price, -limit - current_pos))

                    if current_pos < limit:
                        buy_price = round(fair - BASE_EDGE - K * current_pos)
                        orders.append(Order(product, buy_price, limit - current_pos))

                    return {{product: orders}}, 0, ""
        """)

        tmp_file = Path("_grid_tmp_trader.py")
        keys = list(HYPERPARAMS.keys())
        combos = list(itertools.product(*HYPERPARAMS.values()))
        results = []

        print(f"Grid search: {len(combos)} combos on {round_day}\n")

        for combo in combos:
            params = dict(zip(keys, combo))
            tmp_file.write_text(TRADER_TEMPLATE.format(**params))

            proc = subprocess.run(
                ["uv", "run", "prosperity4btest", str(tmp_file), round_day, "--no-out"],
                capture_output=True, text=True,
            )
            output = proc.stdout + proc.stderr
            match = re.search(r"ASH_COATED_OSMIUM:\s*([\d,\-]+)", output)
            if not match:
                match = re.search(r"Total profit:\s*([\d,\-]+)", output)
            pnl = float(match.group(1).replace(",", "")) if match else float("nan")

            results.append((pnl, params))
            print(f"  base_edge={params['base_edge']:>2}  k={params['k']:<5.2f}  "
                  f"weight={params['weight']:<4.1f}  pnl={pnl:>10,.0f}")

        tmp_file.unlink(missing_ok=True)

        results.sort(key=lambda x: x[0], reverse=True)
        print("\n=== Top 5 combos ===")
        for pnl, params in results[:5]:
            print(f"  pnl={pnl:>10,.0f}  {params}")

        return results

    def run(self, state: TradingState):
        conversions = 0
        result = {}
        result['INTARIAN_PEPPER_ROOT'] = self.pepper_root_strategy(state)
        result['ASH_COATED_OSMIUM'] = self.osmium_strategy(state)
        trader_data = ''

        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data


# if __name__ == "__main__":
#     t = Trader()
#     t.grid_search_pepper_root_strategy("1")