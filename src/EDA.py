import pandas as pd
import matplotlib.pyplot as plt

# 데이터 불러오기
games = pd.read_csv(
    "data/processed/lck_games_2025_2026.csv"
)

actions = pd.read_csv(
    "data/processed/lck_draft_actions_2025_2026.csv"
)

champion_history = pd.read_csv(
    "data/processed/lck_champion_history_2025_2026.csv"
)


print("Games:", len(games))
print("Draft Actions:", len(actions))
print("Champion History:", len(champion_history))

print()
print(games.head())

print()
print(games.info())