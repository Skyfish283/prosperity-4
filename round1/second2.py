from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List


class Trader:
    def run(self, state: TradingState):
        result = {}
        conversions = 0
        traderData_out = ""

        product = "ASH_COATED_OSMIUM"
        limit = 80

        edge = 1

        if product in state.order_depths:
            depth = state.order_depths[product]
            orders: List[Order] = []
            current_pos = state.position.get(product, 0)

            if depth.buy_orders and depth.sell_orders:
                best_bid = max(depth.buy_orders.keys())
                best_ask = min(depth.sell_orders.keys())

                # --- MARKET MAKING LOGIC ---

                # 1. SELL SIDE: Place an order to sell at the best possible price
                # If we aren't at our negative limit, we post a sell order
                if current_pos > -limit:
                    # We try to sell at the current best ask to be competitive
                    sell_price = best_ask
                    # Or, if the spread is wide, we "undercut" by 1
                    if best_ask - best_bid > 2:
                        sell_price = best_ask - edge

                    sell_vol = -limit - current_pos  # How much room we have to sell
                    orders.append(Order(product, sell_price, sell_vol))

                # 2. BUY SIDE: Place an order to buy at the best possible price
                if current_pos < limit:
                    # We try to buy at the current best bid
                    buy_price = best_bid
                    # Or, if the spread is wide, we "penny" the bid (bid + 1)
                    if best_ask - best_bid > 2:
                        buy_price = best_bid + edge

                    buy_vol = limit - current_pos  # How much room we have to buy
                    orders.append(Order(product, buy_price, buy_vol))

            result[product] = orders

        return result, conversions, traderData_out
