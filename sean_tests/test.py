import pandas as pd
import numpy as np

test1 = [x for x in range(50)]

ewm1 = pd.Series(test1).ewm(span=12, adjust=False).mean()
ewm2 = pd.Series(test1).ewm(span=26, adjust=True).mean()
ewm3 = ewm1 - ewm2
print(ewm3.iloc[-1])

print({} is None)