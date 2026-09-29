from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "Popularity_Prestige_Full_18_with_Author_Overview.xlsx"

df = pd.read_excel(DATA_FILE, sheet_name="Full indicators", header=8)
df = df.dropna(subset=["Author"])

print(df.shape)
print(df[["Author", "Gender", "German-original works"]])
