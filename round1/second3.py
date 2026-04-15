from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List


class Trader:
    # Set your optimized parameters here after running the offline factorial test
    OPTIMAL_SPREAD_THRESHOLD = 6
    OPTIMAL_EDGE = 1

    def run(self, state: TradingState):
        result = {}
        conversions = 0
        traderData_out = ""

        product = "ASH_COATED_OSMIUM"
        limit = 80

        if product in state.order_depths:
            depth = state.order_depths[product]
            orders: List[Order] = []
            current_pos = state.position.get(product, 0)

            if depth.buy_orders and depth.sell_orders:
                best_bid = max(depth.buy_orders.keys())
                best_ask = min(depth.sell_orders.keys())
                spread = best_ask - best_bid

                # --- MARKET MAKING LOGIC ---

                # 1. SELL SIDE
                if current_pos > -limit:
                    sell_price = best_ask

                    # Difference for action condition using optimal threshold
                    if spread > self.OPTIMAL_SPREAD_THRESHOLD:
                        sell_price = best_ask - self.OPTIMAL_EDGE

                    sell_vol = -limit - current_pos
                    orders.append(Order(product, sell_price, sell_vol))

                # 2. BUY SIDE
                if current_pos < limit:
                    buy_price = best_bid

                    # Difference for action condition using optimal threshold
                    if spread > self.OPTIMAL_SPREAD_THRESHOLD:
                        buy_price = best_bid + self.OPTIMAL_EDGE

                    buy_vol = limit - current_pos
                    orders.append(Order(product, buy_price, buy_vol))

            result[product] = orders

        return result, conversions, traderData_out
