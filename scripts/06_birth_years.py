from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "Popularity_Prestige_Full_18_with_Author_Overview.xlsx"
FIGURE_FILE = PROJECT_ROOT / "figures" / "fig_birth_decades.png"

df = pd.read_excel(DATA_FILE, sheet_name="Author overview")

years = df["Birth year"].dropna()
print(len(years), "authors with a birth year")

decades = (years // 10 * 10).astype(int).value_counts()
decades = decades.reindex(range(1920, 2000, 10), fill_value=0)
print(decades)

plt.figure(figsize=(7, 4))
plt.bar([f"{d}s" for d in decades.index], decades.values)
plt.xlabel("Decade of birth")
plt.ylabel("Number of authors")
plt.title(f"Birth decades of the authors (n = {len(years)})")
plt.yticks(range(0, int(decades.max()) + 1))
plt.tight_layout()
plt.savefig(FIGURE_FILE, dpi=200)
print("Saved:", FIGURE_FILE)
