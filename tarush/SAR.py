import pandas
import matplotlib.pyplot

data = pandas.read_csv('tarush/prices_round_1_day_0.csv',sep=';')
squid_ink=data[data['product']=="SQUID_INK"]

sar = (squid_ink.iloc[0]['ask_price_1']+squid_ink.iloc[0]['bid_price_1'])/2
af = 0.02
ep = 
sarArray = []

for i in list(range(10000)) :
    sar = sar + af * (ep - sar)
    sarArray.append(sar)

print(sarArray)

