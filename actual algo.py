from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string

class Trader:

    def bid(self):
        return 15
    
    def run(self, state: TradingState):
        """Only method required. It takes all buy and sell orders for all
        symbols as an input, and outputs a list of orders to be sent."""

        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))

        # Orders to be placed on exchange matching engine
        result = {}
        conversions = 0
        
        # --- EMERALDS STRATEGY ---
        # Returns 0 if 'EMERALDS' is not in the position dictionary
        current_position_emeralds = state.position.get('EMERALDS', 0)
        
        orders_emeralds = []
        max_buy_em = max(0, 80 - current_position_emeralds)
        max_sell_em = max(0, current_position_emeralds + 80)
        
        if max_buy_em > 0:
            orders_emeralds.append(Order('EMERALDS', 9995, max_buy_em))
        if max_sell_em > 0:
            orders_emeralds.append(Order('EMERALDS', 10005, -max_sell_em))
            
        if orders_emeralds:
            result['EMERALDS'] = orders_emeralds
    
        # --- TOMATOES STRATEGY ---
        current_position_tomatoes = state.position.get('TOMATOES', 0)
        
        # Initialize default values
        curr_tomato_price = 10000.0 # Default mid price
        traderData_out = "10000.0"  # Default return data

        # Check if TOMATOES exists and has orders
        if 'TOMATOES' in state.order_depths:
            depth = state.order_depths['TOMATOES']
            if depth.buy_orders and depth.sell_orders:
                best_bid = max(depth.buy_orders.keys())
                best_ask = min(depth.sell_orders.keys())
                curr_tomato_price = (best_bid + best_ask) / 2
                
                max_buy_tm = max(0, 80 - current_position_tomatoes)
                max_sell_tm = max(0, current_position_tomatoes + 80)

                # Handle traderData safely
                prev_tomato_price = None
                if state.traderData and state.traderData != '':
                    try:
                        # Use float instead of int to handle decimal prices
                        prev_tomato_price = float(state.traderData)
                    except ValueError:
                        prev_tomato_price = None

                if prev_tomato_price is not None and prev_tomato_price != 0:
                    returns = (curr_tomato_price - prev_tomato_price) / prev_tomato_price
                    
                    if returns > 0:
                        if max_buy_tm > 0:
                            result['TOMATOES'] = [Order('TOMATOES', int(curr_tomato_price), max_buy_tm)]
                    else:
                        if max_sell_tm > 0:
                            result['TOMATOES'] = [Order('TOMATOES', int(curr_tomato_price), -max_sell_tm)]
                else:
                    # First tick or invalid previous data: Place neutral order or wait
                    # Here we place a buy order at mid to establish presence
                    if max_buy_tm > 0:
                        result['TOMATOES'] = [Order('TOMATOES', int(curr_tomato_price), max_buy_tm)]
                
                # Update traderData for next tick
                traderData_out = str(curr_tomato_price)
            else:
                # No buy/sell orders available, keep old traderData or default
                traderData_out = state.traderData if state.traderData else "10000.0"
        else:
            # TOMATOES not in order depths
            traderData_out = state.traderData if state.traderData else "10000.0"

        return result, conversions, traderData_out