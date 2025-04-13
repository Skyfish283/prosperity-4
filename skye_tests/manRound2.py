import random
import matplotlib.pyplot as plt

# Game setup
num_crates = 10
num_players = 1000
coins_per_box = 10000
entry_fee = 50000

# Box multipliers (example values)
crates = {
    1: 10,
    2: 17,
    3: 20,
    4: 31,
    5: 37,
    6: 50,
    7: 73,
    8: 80,
    9: 89,
    10: 90
}

# Pre-chosen players before the game starts
players_chosen = {
    1: 1,
    2: 1,
    3: 2,
    4: 2,
    5: 3,
    6: 4,
    7: 4,
    8: 6,
    9: 8,
    10: 10
}

# Simulate player decisions
player_choices = []
greedy_ratio = 0.8  # 30% of players use greedy strategy

for _ in range(num_players):
    is_greedy = random.random() < greedy_ratio
    available_crates = list(crates.keys())

    if is_greedy:
        # Estimate expected value for each box assuming current known players + self
        expected_values = {
            box: (crates[box] * coins_per_box) / (players_chosen.get(box, 0) + 1)
            for box in crates
        }
        # Choose top 2 distinct crates
        sorted_crates = sorted(expected_values.items(), key=lambda x: -x[1])
        box1 = sorted_crates[0][0]
        for box, _ in sorted_crates:
            if box != box1:
                box2 = box
                break
    else:
        # Random strategy: pick 2 distinct crates randomly
        box1, box2 = random.sample(available_crates, 2)

    # Record choices
    player_choices.append((box1, box2))

    # Update players_chosen for both crates
    players_chosen[box1] = players_chosen.get(box1, 0) + 1
    players_chosen[box2] = players_chosen.get(box2, 0) + 1

# Calculate expected value per player based on their chosen boxes
player_values = []

for box1, box2 in player_choices:
    value1 = (crates[box1] * coins_per_box) / players_chosen[box1]
    value2 = (crates[box2] * coins_per_box) / players_chosen[box2]
    total_value = value1 + value2 - entry_fee  # only second box has fee
    player_values.append(total_value)

# Plot histogram of player values
plt.figure(figsize=(10, 6))
plt.hist(player_values, bins=30, color='skyblue', edgecolor='black')
plt.xlabel("Net Value per Player")
plt.ylabel("Number of Players")
plt.title("Distribution of Player Value (Revenue - Cost)")
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.show()
    

# Final count of players per box
final_players_per_box = [players_chosen[i] for i in range(1, num_crates + 1)]

# Plot the result
plt.figure(figsize=(10, 6))
plt.bar(range(1, num_crates + 1), final_players_per_box, color='skyblue')
plt.xlabel("Box Number")
plt.ylabel("Number of Players Choosing the Box")
plt.title("Number of Players per Box After Simulation")
plt.xticks(range(1, num_crates + 1))
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.show()
