# test MACD on day 0 squid ink data
# the squid dataframe must have integer indicies 0,1,2... before conduting analysis
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

#pd.set_option('display.max_rows', 500)
#pd.set_option('display.max_columns', 500)
#pd.set_option('display.width', 1000)

def lookback(series, index, curr_val):
    for i in range(0, index, -1):
        if curr_val == 1 and series.loc[i] < 0:
            return 1
        elif curr_val == -1 and series.loc[i] > 0:
            return -1
    return 0

def MACD_match(MACD_list, n, percentage):
    # check if any value in MACD_list is within the specified percentage of n
    for val in MACD_list:
        if abs(val - n) <= abs(percentage * n):
            return True
    return False
    
def crossover_analysis(series, crossover_series):
    first_run = True
    for idx, val in series.items():
        if first_run or val == 0:
            crossover_series.loc[idx] = 0
            first_run = False
        elif val > 0:
            if series.loc[idx - 1] < 0: # bullish crossover
                crossover_series.loc[idx] = 1
            elif series.loc[idx - 1] > 0: # no crossover
                crossover_series.loc[idx] = 0
            else: # MACD histogram is 0, check further behind for crossover
                crossover_series.loc[idx] = lookback(series, idx, 1)
        elif val < 0:
            if series.loc[idx - 1] > 0: # bearish crossover
                crossover_series.loc[idx] = -1
            elif series.loc[idx - 1] < 0: # no crossover
                crossover_series.loc[idx] = 0
            else:
                crossover_series.loc[idx] = lookback(series, idx, -1)
    return crossover_series

def MACD(csv_data, ema_fast=12, ema_slow=26, ema_sig=9):
    df = pd.read_csv(csv_data, sep=';')
    squid = df.loc[df['product'] == 'SQUID_INK'].copy()
    #print(squid.head())
    #print(squid['mid_price'])
    if squid['mid_price'].count() < (ema_fast + ema_slow):
        raise Exception("Insufficient data to calculate MACD")
    # EMA lines
    squid['EMA_fast'] = squid['mid_price'].ewm(span=ema_fast, adjust=False).mean()
    squid['EMA_slow'] = squid['mid_price'].ewm(span=ema_slow, adjust=False).mean()
    # MACD line
    squid['MACD'] = squid['EMA_fast'] - squid['EMA_slow']
    # signal line (EMA of MACD line)
    squid['signal'] = squid['MACD'].ewm(span=ema_sig, adjust=False).mean()
    squid['hist'] = squid['MACD'] - squid['signal']

    # now reset index of squid to be integers 0,1,2...
    squid.reset_index(drop=True, inplace=True)
    # print(squid.head())
    # now implement different signals: signal-line crossover, zero crossover, divergence
    # 1 for bullish, 0 for neutral (no signal), -1 for bearish

    # could separate each series into two (bullish and bearish) so that each series is boolean
    signal_crossover = pd.Series(0, index=squid.index)
    zero_crossover = pd.Series(0, index=squid.index)
    divergence = pd.Series(0, index=squid.index)

    signal_crossover = crossover_analysis(squid['signal'], signal_crossover)
    print(signal_crossover.value_counts())
    zero_crossover = crossover_analysis(squid['MACD'], zero_crossover)
    print(zero_crossover.value_counts())

    min_div_runs = 10 # minimum number of runs to consider divergence; need enough data for max and min price to be meaningful
    div_runs = 0
    max_price = 0
    min_price = 0
    MACD_max = 0
    MACD_min = 0
    past_5_MACD = []
    for idx, row in squid.iterrows():
        if len(past_5_MACD) > 5:
            past_5_MACD = past_5_MACD[1:]
        past_5_MACD.append(row["MACD"])

        if div_runs < min_div_runs:
            if div_runs == 0: # initialise prices for first run
                # print(row["mid_price"])
                max_price = row["mid_price"]
                min_price = row["mid_price"]
                MACD_max = row["MACD"]
                MACD_min = row["MACD"]
            div_runs += 1
            continue
        # now update min/max prices
        if row["mid_price"] > max_price:
            max_price = row["mid_price"]
        if row["mid_price"] < min_price:
            min_price = row["mid_price"]
        if row["MACD"] > MACD_max:
            MACD_max = row["MACD"]
        if row["MACD"] < MACD_min:
            MACD_min = row["MACD"]

        # now check for divergence

        # for MACD, could check a neighbourhood of values
        if row["mid_price"] == max_price and not MACD_match(past_5_MACD, MACD_max, 0.1): 
            # new high not confirmed by MACD, bearish divergence
            divergence.loc[idx] = -1
        elif row["mid_price"] == min_price and not MACD_match(past_5_MACD, MACD_min, 0.1):
            # new low not confirmed by MACD, bullish divergence
            divergence.loc[idx] = 1
    print(divergence.value_counts())

    # plotting TBD (would be easier if the series are separated into boolean ones)
    plt.scatter(x=squid['timestamp'], y=signal_crossover, color='red', label='signal crossover')
    plt.scatter(x=squid['timestamp'], y=divergence, color='blue', label='divergence')
    plt.show()
MACD('sean_tests/prices_round_1_day_0.csv')