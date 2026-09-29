from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from adjustText import adjust_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "Popularity_Prestige_Full_18_with_Author_Overview.xlsx"
FIGURE_FILE = PROJECT_ROOT / "figures" / "fig_goodreads_prizes.png"

# Load the author-level indicators.
df = pd.read_excel(DATA_FILE, sheet_name="Full indicators", header=8)
df = df.dropna(subset=["Author"])

# Keep only authors with both values (blank = missing, not zero).
data = df.dropna(subset=["Goodreads ratings", "Literary-field prizes"])
n = len(data)
rho = data["Goodreads ratings"].corr(
    data["Literary-field prizes"], method="spearman"
)

fig, ax = plt.subplots(figsize=(9, 6.5))
ax.scatter(data["Goodreads ratings"], data["Literary-field prizes"])

# A symmetric logarithmic scale spreads out large values while retaining zero.
ax.set_xscale("symlog")

# Authors on exactly the same point share one label.
labels = (
    data.groupby(["Goodreads ratings", "Literary-field prizes"])["Author"]
    .apply(" / ".join)
    .reset_index()
)

texts = []
for _, row in labels.iterrows():
    texts.append(
        ax.text(
            row["Goodreads ratings"],
            row["Literary-field prizes"],
            row["Author"],
            fontsize=8,
        )
    )

adjust_text(
    texts,
    ax=ax,
    arrowprops=dict(arrowstyle="-", color="gray", lw=0.5),
)

ax.set_xlabel("Goodreads ratings (symmetric log scale)")
ax.set_ylabel("Literary-field prizes")
fig.suptitle(
    "Popularity and prestige: Goodreads ratings vs literary prizes",
    fontsize=12,
)
ax.set_title(f"Spearman correlation = {rho:.2f}; n = {n}", fontsize=10)

fig.text(
    0.01,
    0.01,
    "Note: Shani Katayun and May Atashkar are excluded because their "
    "prize values are missing. Verified zeros remain included.",
    fontsize=8,
    style="italic",
)

fig.tight_layout(rect=[0, 0.04, 1, 1])
fig.savefig(FIGURE_FILE, dpi=200)
print(n, "authors plotted; Spearman =", round(rho, 2))
print("Saved:", FIGURE_FILE)
