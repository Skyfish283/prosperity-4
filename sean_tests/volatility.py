# test volatility calculations (scuffed)
import pandas as pd
import numpy as np
import math

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


if __name__ == "__main__":
    csv_list = ['prices_round_1_day_0.csv','prices_round_1_day_-1.csv',
                'prices_round_1_day_-2.csv']
    print(calc_vol_day(csv_list[0]))
    '''for file in csv_list:
        print(calc_vol_day(file, mode=1, freq_per_day=2))
        print(calc_vol_day(file))'''
