from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string


class Trader:
    def run(self, state: TradingState):
        result = {}
        conversions = 0
        traderData_out = "10000.0"  # Default return data

        product = "ASH_COATED_OSMIUM"

        # 1. Define your mean (fair value) and position limits
        fair_value = 10000.0
        POSITION_LIMIT = 80

        if product in state.order_depths:
            depth = state.order_depths[product]
            orders: List[Order] = []

            # Get current inventory position
            current_position = state.position.get(product, 0)

            if depth.buy_orders and depth.sell_orders:
                best_bid = max(depth.buy_orders.keys())
                best_ask = min(depth.sell_orders.keys())

                # 2. BUY LOGIC: If the asking price is below our mean, it's cheap!
                if best_ask < fair_value:
                    # Calculate how much we can buy without breaching the limit
                    buy_volume = POSITION_LIMIT - current_position

                    if buy_volume > 0:
                        print(f"BUYING: Price {best_ask} is below mean {fair_value}")
                        # In this system, Buy orders have positive volume
                        orders.append(Order(product, best_ask, buy_volume))

                # 3. SELL LOGIC: If the bidding price is above our mean, it's expensive!
                elif best_bid > fair_value:
                    # Calculate how much we can sell without breaching the negative limit (-20)
                    # Example: if limit is 20, and we hold 5, we can sell 25 (to reach -20)
                    # So: (-20) - 5 = -25 volume
                    sell_volume = (-POSITION_LIMIT) - current_position

                    if sell_volume < 0:
                        print(f"SELLING: Price {best_bid} is above mean {fair_value}")
                        # In this system, Sell orders have negative volume
                        orders.append(Order(product, best_bid, sell_volume))

            # Attach our list of orders to the product in the result dictionary
            result[product] = orders

        return result, conversions, traderData_out
