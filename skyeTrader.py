from datamodel import *
from typing import *
import string
from statistics import *
import json
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
    
    def run(self, state: TradingState):
        # print internal state and market info
        #print("traderData: " + state.traderData)
        #print("Observations: " + str(state.observations))
        #dictionary to store orders for each product
        result = {}

        #use historic data
        max_past_data = 1000

        try:
            past_data = json.loads(state.traderData)
        except:
            past_data = {}
        finally:
            print("data retrieved from traderdata. ")

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []

            if len(order_depth.sell_orders)== 0 or len(order_depth.buy_orders) == 0:
                result[product] = orders#if no sell or no buy--> no trading
                continue

            buy_orders = order_depth.buy_orders
            sell_orders = order_depth.sell_orders

            #print("Buy Order depth : " + str(len(order_depth.buy_orders)) + ", Sell order depth : " + str(len(order_depth.sell_orders)))
            
            # calculate acceptable price
            best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]
            best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]

            spread = best_ask - best_bid
            mid_price = (best_ask+best_bid)/2

            #update past data
            past_prices = past_data.get(product, [])
            if past_prices == []:
                past_data[product]= []
            past_data[product].append(mid_price)
            past_prices.append(mid_price)
            if len(past_prices) > max_past_data:
                past_prices = past_prices[-max_past_data:] #control under max data size
                past_data[product] = past_prices
            

            max_position = 50
            pos = state.position.get(product, 0) #get the position for current product

            
            if len(past_prices)> 1:
                voltatility = stdev(past_prices)
                mean_price = mean(past_prices)
            else:
                voltatility = 1
                mean_price = past_prices[0]
                

            #inventory aware pricing: owning (long) or short
            skew = pos/max_position * 5
            acceptable_buy = mean_price-voltatility - skew #if skew>0, more eager to sell, if skew<0 more eager to buy
            acceptable_sell = mean_price+voltatility - skew 
            logger.print("Acceptable buy : " + str(acceptable_buy) + ", Acceptable sell : "+str(acceptable_sell))
            
            #buying opportunities
            if best_ask <= acceptable_buy:
                volume = min(-sell_orders[best_ask], max_position - pos)
                if volume > 0:
                    logger.print("BUY", str(-volume) + "x", best_ask)
                    orders.append(Order(product, best_ask, volume))
                    pos += volume
            
            #selling opportunities
            if best_bid >= acceptable_sell:
                volume = min(buy_orders[best_bid], max_position + pos)
                if volume > 0:
                    logger.print("SELL", str(volume) + "x", best_bid)
                    orders.append(Order(product, best_bid, -volume))
                    pos -= volume   
            result[product] = orders
    
    
        traderData = json.dumps(past_data) # String value holding Trader state data required. It will be delivered as TradingState.traderData on next execution.
        
        conversions = 0
        logger.flush(state,result,None,traderData)
        return result, conversions, traderData
