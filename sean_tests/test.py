import pandas as pd
import numpy as np

test1 = [x for x in range(50)]

ewm1 = pd.Series(test1).ewm(span=12, adjust=False).mean()
ewm2 = pd.Series(test1).ewm(span=26, adjust=True).mean()
ewm3 = ewm1 - ewm2
print(ewm3.iloc[-1])

print([x for x in range(-1, -5, -1)])

print(any([x < 0 for x in [y for y in range(0, 5)]]))

volatility = 1.0
Z = np.random.normal(0, 1, 1000000)
S = 1950
K = 2000
T = 5 # 5 days from beginning of round 3 to expiry
r = 0
S_T = S * np.exp((r - (volatility ** 2) / 2) * T + volatility * np.sqrt(T) * Z)
payoffs = np.maximum(S_T - K, 0)
print(type(payoffs))