# test volatility calculations (scuffed)
import pandas as pd
import numpy as np
import math
from typing import *

pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

def round_100(num):
    return int(round(num, -2))

def calc_vol_day(csv_file, mode=0, freq_per_day=1):
    # mode 0 -> calculate volatility of mid price for each product per day
    # mode 1 -> split a day into a set number of intervals and calculate volatility for each
    variance_mat = []
    variance_list = []
    df = pd.read_csv(csv_file,sep=";")
    product_list = df['product'].unique()
    if mode == 0 or freq_per_day == 1:
        for product in product_list:
            variance = df.loc[df['product'] == product, 'mid_price'].var()
            variance_list.append(round(variance,4))
        stdev_list = np.sqrt(variance_list)
        print(dict(zip(product_list, stdev_list)))
        return dict(zip(product_list, variance_list))

    elif mode == 1 and freq_per_day > 1:
        max_timestamp = df['timestamp'].max()
        intervals_list = [[round_100(x / freq_per_day * max_timestamp),
                           round_100((x + 1)/ freq_per_day * max_timestamp)]
                          for x in range(0, freq_per_day)]
        for interval in intervals_list:
            variance_interval = []
            df_interval = df[(df['timestamp'] >= interval[0]) & (df['timestamp'] < interval[1])]
            for product in product_list:
                variance = df_interval.loc[df_interval['product'] == product, 'mid_price'].var()
                variance_interval.append(round(variance, 4))
            variance_dict = dict(zip(product_list, variance_interval))
            variance_mat.append(variance_dict)
        return variance_mat

def beta(csv_file, products_weights : Dict[str, float], basket: str):
    df = pd.read_csv(csv_file, sep=";")
    basket_prices = df.loc[df['product'] == basket, 'mid_price'].reset_index(drop=True)
    basket_returns = pd.Series(0.0, index=basket_prices.index)
    for idx, val in basket_prices.items():
        if idx == 0:
            continue
        basket_returns[idx] = (val - basket_prices[idx - 1]) / basket_prices[idx - 1]

    basket_returns_var = basket_returns.var()
    cov_list : List[float]= []
    beta_list : List[float] = []
    for product, weight in products_weights.items():
        # Assuming timestamp column exists
        product_prices = df.loc[df['product'] == product, 'mid_price'].reset_index(drop=True)
        product_returns = pd.Series(0.0, index=product_prices.index)
        for idx, val in product_prices.items():
            if idx == 0:
                continue
            product_returns[idx] = (val - product_prices[idx - 1]) / product_prices[idx - 1]
        cov = product_returns.cov(basket_returns)
        '''product_df = df[df['product'] == product][['timestamp', 'mid_price']]
        basket_df = df[df['product'] == basket][['timestamp', 'mid_price']]
        merged_df = pd.merge(product_df, basket_df, on='timestamp', suffixes=(f'_{product.lower()}', '_basket'))
        print(merged_df)
        cov = merged_df[f'mid_price_{product.lower()}'].cov(merged_df['mid_price_basket'])'''
        cov_list.append(cov)
        # print(cov_list)
        beta_list.append(cov / basket_returns_var)
    beta_list = dict(zip(products_weights.keys(), beta_list))
    return beta_list

if __name__ == "__main__":
    csv_list = ['prices_round_1_day_0.csv','prices_round_1_day_-1.csv',
                'prices_round_1_day_-2.csv']
    csv_list_day2 = ['sean_tests/prices_day_-1.csv', 'sean_tests/prices_day_0.csv',
                     'sean_tests/prices_day_1.csv']
   # print(calc_vol_day(csv_list[0]))
    print(calc_vol_day(csv_list_day2[2]))
   # for i in range(3):
   #     print(beta(csv_list_day2[i], {'CROISSANTS': 4/6, 'JAMS': 1/3}, 'PICNIC_BASKET2'))
   # for file in csv_list_day2:
   #     print(calc_vol_day(file))
