import pandas as pd
import matplotlib.pyplot as plt

# Define the file paths
price_files = [
    "prices_round_2_day_-1.csv",
    "prices_round_2_day_0.csv",
    "prices_round_2_day_1.csv",
]
trade_files = [
    "trades_round_2_day_-1.csv",
    "trades_round_2_day_0.csv",
    "trades_round_2_day_1.csv",
]

# Load and combine price files
prices_list = []
for f in price_files:
    df = pd.read_csv(f, sep=";")
    prices_list.append(df)
prices = pd.concat(prices_list, ignore_index=True)

# Load and combine trade files (adding the 'day' column to align with prices)
trades_list = []
for day, f in zip([-1, 0, 1], trade_files):
    df = pd.read_csv(f, sep=";")
    df["day"] = day
    trades_list.append(df)
trades = pd.concat(trades_list, ignore_index=True)

# Create a continuous time column by offsetting the timestamp by the day
prices["time"] = prices["day"] * 1000000 + prices["timestamp"]
trades["time"] = trades["day"] * 1000000 + trades["timestamp"]

products = prices["product"].unique()

# Plot 1: Mid price, Best Ask, Best Bid & Overlaid Trades
plt.figure(figsize=(15, 10))
for i, product in enumerate(products, 1):
    plt.subplot(2, 1, i)
    p_data = prices[prices["product"] == product]
    t_data = trades[trades["symbol"] == product]

    # Plot bid, ask and mid prices
    plt.plot(p_data["time"], p_data["mid_price"], label="Mid Price", color="blue")
    plt.plot(
        p_data["time"],
        p_data["ask_price_1"],
        label="Best Ask (Lowest)",
        color="red",
        alpha=0.5,
    )
    plt.plot(
        p_data["time"],
        p_data["bid_price_1"],
        label="Best Bid (Highest)",
        color="green",
        alpha=0.5,
    )

    # Overlay the executed trades
    plt.scatter(
        t_data["time"],
        t_data["price"],
        color="black",
        marker="x",
        label="Trades",
        alpha=0.7,
    )

    plt.title(f"Prices and Trades: {product}")
    plt.xlabel("Continuous Time (day * 1,000,000 + timestamp)")
    plt.ylabel("Price")
    plt.legend()

plt.tight_layout()
plt.show()

# Plot 2: Normalized mid prices
plt.figure(figsize=(15, 5))
for product in products:
    p_data = prices[prices["product"] == product].copy()

    # Normalize by dividing by the very first mid_price of Day -1
    first_price = p_data["mid_price"].iloc[0]
    p_data["normalized_price"] = p_data["mid_price"] / first_price

    plt.plot(p_data["time"], p_data["normalized_price"], label=product)

plt.title("Normalized Mid Prices")
plt.xlabel("Continuous Time (day * 1,000,000 + timestamp)")
plt.ylabel("Normalized Price (Base = 1.0)")
plt.legend()
plt.tight_layout()
plt.show()
