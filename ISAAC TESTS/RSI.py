from datamodel import *
from typing import *
import string
from statistics import *
import math
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

    def RSI(self, state: TradingState, product: str, data: Dict[str,Dict[str,List[float]]]) -> List[Order]:
        asks= list(state.order_depths[product].sell_orders.items())
        bids= list(state.order_depths[product].buy_orders.items())
        best_ask = asks[0][0]
        best_bid = bids[0][0]

        ## OUR RSI CALC
        if data.get(product, {}) == {}:
            data[product] = {"prev_mid": (best_ask+best_bid)/2,"past_up":[],"past_down":[]}
            rsi = 50
        else:
            if data[product]["prev_mid"] < (best_ask+best_bid)/2:
                data[product]["past_up"].append((best_ask+best_bid)/2-data[product]["prev_mid"])
            elif data[product]["prev_mid"] > (best_ask+best_bid)/2:
                data[product]["past_down"].append( abs((best_ask+best_bid)/2-data[product]["prev_mid"]) )

            
            if len(data[product]["past_up"]) > 14:
                del data[product]["past_up"][0]
            if len(data[product]["past_down"]) > 14:
                del data[product]["past_down"][0]

            data[product]["prev_mid"] = (best_ask+best_bid)/2
            if len(data[product]["past_up"]) > 1 and len(data[product]["past_down"]) > 1:
                rsi = 100-(100 / (1 + mean(data[product]["past_up"]) / mean(data[product]["past_down"]) ) )
            else:
                rsi = 50

        ideal_position = 250-5*rsi
        logger.print("RSI: ",rsi)
        diff = ideal_position-state.position.get(product,0)

        if diff > 50:
            diff = 50
        if diff < -50:
            diff = -50
        
                    
        orders: List[Order] = []
        if diff < 0:
            for ask,amt in asks:
                orders.append(Order(product, ask, min(diff,-amt)))
                logger.print("BUYING ", max(diff,-amt), "UNITS AT ", ask)
                diff += amt
                if diff <=0:
                    break
        else:
            for bid,amt in bids:
                orders.append(Order(product, bid, max(diff,-amt)))
                logger.print("SELLING ", max(diff,-amt), "UNITS AT ", bid)
                diff += amt
                if diff <=0:
                    break
        
        return orders

        
    def find_reservation_and_spread(self, product: Product, state: TradingState, past_week: List[float]) -> List[float]:
        if past_week == []:
            return [-1,-1]
        elif len(past_week) == 1:
            return past_week[0],1
        else:
            mid = mean(past_week)
            var = variance(past_week)
            position = state.position.get(product,0)
            gamma = 1e-4
            tprop = 0.95
            k = math.log(2)/0.01
            
            return mid-var*position*gamma*tprop, 2/gamma*math.log(1+gamma/k)+gamma*var
    
    def mm(self, state: TradingState, product: str, data: Dict[str,Dict[str,List[float]]]) -> List[Order]:
        best_ask, best_ask_amount = list(state.order_depths[product].sell_orders.items())[0]
        best_bid, best_bid_amount = list(state.order_depths[product].buy_orders.items())[0]

        if data.get(product, {}) == {}:
            data[product] = {"prev_mid": [(best_ask+best_bid)/2]}
        else:
            data[product]["prev_mid"].append((best_ask+best_bid)/2)

        if (len(data[product]["prev_mid"]) > 14):
            del data[product]["prev_mid"][0]

        orders: List[Order] = []
        # just around right these values def need adjusting -- find through AS
        res, spread = self.find_reservation_and_spread(product,state,data[product]["prev_mid"])

        if (res == -1):
            res = (best_ask+best_bid)/2
            spread = 1

        spread = min(spread,1)
        max_ask = round(res-spread)
        min_bid = round(res+spread)


        if int(best_ask) <= max_ask:
            orders.append(Order(product, best_ask, -best_ask_amount))

        if int(best_bid) >= min_bid:
            orders.append(Order(product, best_bid, -best_bid_amount))

        return orders


    
    def run(self, state: TradingState):

        maxpos = {'RAINFOREST_RESIN': 50, 'KELP': 50, 'SQUID_INK': 50}
        result = {}

        if state.traderData == "":
            data : Dict[str,Dict[str,List[float]]] = {}
        else:
            data : Dict[str,Dict[str,List[float]]] = json.loads(state.traderData)
        
        result['KELP'] = self.RSI(state,'KELP', data)
        result['SQUID_INK'] = self.RSI(state,'SQUID_INK', data)
        result['RAINFOREST_RESIN'] = self.mm(state, 'RAINFOREST_RESIN', data)

        traderData = json.dumps(data)

        logger.flush(state,result,None,traderData)

        conversions = None
        return result, conversions, traderData
