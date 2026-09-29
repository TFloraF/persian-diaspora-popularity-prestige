from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "Popularity_Prestige_Full_18_with_Author_Overview.xlsx"

df = pd.read_excel(DATA_FILE, sheet_name="Full indicators", header=8)
df = df.dropna(subset=["Author"])

cols = {
    "Wiki length (bytes)": "wiki_len",
    "Wiki pageviews": "wiki_views",
    "Wiki revisions": "wiki_edits",
    "Goodreads ratings": "goodreads",
    "Literary-field prizes": "prizes",
    "DNB secondary works": "dnb",
}
data = df[list(cols)].rename(columns=cols)

print("Values available per indicator:")
print(data.count())
print()
print(data.corr(method="spearman").round(2))
