from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "Popularity_Prestige_Full_18_with_Author_Overview.xlsx"
FIGURE_FILE = PROJECT_ROOT / "figures" / "fig_wiki_length.png"

df = pd.read_excel(DATA_FILE, sheet_name="Full indicators", header=8)
df = df.dropna(subset=["Author"])

data = df.sort_values("Wiki length (bytes)", ascending=False)

plt.figure(figsize=(10, 5))
plt.bar(data["Author"], data["Wiki length (bytes)"])
plt.xticks(rotation=70, ha="right")
plt.ylabel("German Wikipedia article length (bytes)")
plt.title("Wikipedia article length per author")
plt.tight_layout()
plt.savefig(FIGURE_FILE, dpi=200)
print("Saved:", FIGURE_FILE)
