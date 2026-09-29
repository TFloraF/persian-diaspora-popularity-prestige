from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "Popularity_Prestige_Full_18_with_Author_Overview.xlsx"

df = pd.read_excel(DATA_FILE, sheet_name="Full indicators", header=8)
df = df.dropna(subset=["Author"])

print(df["Gender"].value_counts())
print()
print(df["Generation"].value_counts())
print()

works = df["German-original works"]
print("Total works:", works.sum())
print("Median per author:", works.median())
print("Min:", works.min(), "Max:", works.max())
