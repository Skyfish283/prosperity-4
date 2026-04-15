from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string


class Trader:
    def __init__(self):
        self.limits = {
            'INTARIAN_PEPPER_ROOT': 80,
            'ASH_COATED_OSMIUM': 80
        }

    def bid(self):
        return 15
    

    def pepper_root_strategy(self, state):
        fair = 13000 + 1000 * (state.timestamp / 1000000)
        pos = state.position.get('INTARIAN_PEPPER_ROOT', 0)
        orders = []
    
        # --- BUY SIDE ---
        # Capacity: how far we are from the +80 long limit
        buy_capacity = 80 - pos
    
        buy_levels = [
            (int(fair),     4),
            (int(fair) - 1, 6),
            (int(fair) - 2, 8),
            (int(fair) - 3, 10),
            (int(fair) - 4, 5),
        ]
    
        remaining_buy = buy_capacity
        for price, qty in buy_levels:
            actual_qty = min(qty, remaining_buy)
            if actual_qty > 0:
                orders.append(Order('INTARIAN_PEPPER_ROOT', price, actual_qty))
                remaining_buy -= actual_qty
            if remaining_buy <= 0:
                break
    
        # --- SELL SIDE ---
        # Capacity: how far we are from the -80 short limit
        sell_capacity = pos + 80
    
        # Selling today costs us tomorrow's drift (+1), so fair+1 is break-even.
        # We only want to sell if price is sufficiently above that opportunity cost.
        # Deeper asks = better edge = justified larger size (marginal cost curve).
        sell_levels = [
            (int(fair) + 2, 4),   # +1 above break-even, thin edge
            (int(fair) + 3, 6),   # solid edge
            (int(fair) + 4, 8),   # good edge
            (int(fair) + 5, 10),  # matches what sellers typically ask — sweet spot
            (int(fair) + 6, 5),   # deep ask, free edge if hit
        ]
    
        remaining_sell = sell_capacity
        for price, qty in sell_levels:
            actual_qty = min(qty, remaining_sell)
            if actual_qty > 0:
                orders.append(Order('INTARIAN_PEPPER_ROOT', price, -actual_qty))  # negative = sell
                remaining_sell -= actual_qty
            if remaining_sell <= 0:
                break
    
        return orders
    
    def osmium_strategy(self, state):
        OPTIMAL_SPREAD_THRESHOLD = 6
        OPTIMAL_EDGE = 1
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
                    if spread > OPTIMAL_SPREAD_THRESHOLD:
                        sell_price = best_ask - OPTIMAL_EDGE
 
                    sell_vol = -limit - current_pos
                    orders.append(Order(product, sell_price, sell_vol))
 
                # 2. BUY SIDE
                if current_pos < limit:
                    buy_price = best_bid
 
                    # Difference for action condition using optimal threshold
                    if spread > OPTIMAL_SPREAD_THRESHOLD:
                        buy_price = best_bid + OPTIMAL_EDGE
 
                    buy_vol = limit - current_pos
                    orders.append(Order(product, buy_price, buy_vol))
 
        return orders
    
        
    def run(self, state: TradingState):
        conversions = 0
        result = {}
        result['INTARIAN_PEPPER_ROOT'] = self.pepper_root_strategy(state)
        result['ASH_COATED_OSMIUM'] = self.osmium_strategy(state)

        trader_data = ''

        return result, conversions, trader_data
