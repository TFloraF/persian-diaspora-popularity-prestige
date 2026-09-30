# Popularity and Prestige among German-Language Persian-Diaspora Authors

This repository contains the data, scripts, and figures for a metadata study of 18 German-language authors with an Iranian/Persian diaspora background in Germany, Austria, and Switzerland.

The project asks:

> How are measured popularity and prestige related among German-language Persian-diaspora authors in the DACH region?

The study is descriptive. It does not claim to identify a complete literary canon or to represent every author in this field.

## Dataset

The final corpus contains:

- 18 authors
- 119 distinct German-original literary works
- 11 women, 6 men, and 1 nonbinary author
- 15 first-generation and 3 second-generation authors under the study's operational definition

Popularity is represented by German Wikipedia article length, Wikipedia pageviews, Wikipedia revisions, and Goodreads rating counts. Prestige is represented by verified literary-field prizes and DNB-linked secondary records.

The indicators are imperfect proxies. In particular, the three Wikipedia measures are related to one another, Goodreads coverage is uneven, and recent authors may have little DNB-linked secondary coverage.

## Repository structure

```text
data/
  author_catalog_coverage.csv
  Persian_German_Works_Final_Audited.xlsx
  Popularity_Prestige_Full_18_with_Author_Overview.xlsx

figures/
  fig_birth_decades.png
  fig_goodreads_prizes.png
  fig_wiki_length.png

scripts/
  pull_works_data.py
  pull_indicators.py
  01_load.py
  02_overview.py
  03_wiki_chart.py
  04_correlation.py
  05_scatter.py
  06_birth_years.py

requirements.txt
```

`author_catalog_coverage.csv` contains the 19 candidates examined during the author audit. The initial pull script selects the frozen corpus of 18 authors. Bahman Nirumand remains in the audit input as a documented exclusion under the project's operational criteria.

## Workflow

1. Candidate authors were checked against explicit inclusion criteria.
2. `pull_works_data.py` retrieved an initial set of DNB catalogue records and Wikidata metadata.
3. Catalogue records were provisionally grouped by normalized title.
4. Ambiguous groups were checked manually against DNB records and external evidence.
5. Editions and formats of the same work were grouped. Translations into German were retained in the raw evidence but excluded from the German-original work count.
6. Missing values were kept distinct from verified zero values.
7. Wikipedia article existence, length, revisions, pageviews, and raw DNB-linked secondary records were collected programmatically with `pull_indicators.py`. Goodreads ratings and literary-prize evidence were checked manually; their URLs and evidence notes are stored in the indicator workbook.
8. DNB-linked records were grouped and reviewed to estimate distinct secondary works. Popularity and prestige indicators were then compared descriptively using Spearman rank correlations.

The initial pull script does **not** produce the final audited work count by itself. Its automatic classifications were provisional. Manual review exposed additional translation statements, older literary classification codes, anthology contributions, and revised-edition questions. The final decisions and supporting notes are recorded in `Persian_German_Works_Final_Audited.xlsx`.

Similarly, `pull_indicators.py` retrieves raw eligible DNB-linked secondary records, not the final distinct-secondary-work count. Editions and formats were grouped afterwards and ambiguous records were reviewed. These decisions and their supporting evidence are recorded in `Popularity_Prestige_Full_18_with_Author_Overview.xlsx`.

## Running the analysis

Create a Python environment and install the packages listed in `requirements.txt`. From the repository's main directory, run:

```bash
python scripts/01_load.py
python scripts/02_overview.py
python scripts/03_wiki_chart.py
python scripts/04_correlation.py
python scripts/05_scatter.py
python scripts/06_birth_years.py
```

The chart scripts save their output in `figures/`.

`pull_works_data.py` is the original first-stage retrieval script. It requires an internet connection and reads `data/author_catalog_coverage.csv`. Running it creates a new initial pull; it does not reproduce the later manual verification decisions automatically.

`pull_indicators.py` also requires an internet connection. Without an option it runs the original three-author pilot. To retrieve the automated indicators for the complete 18-author corpus, run:

```bash
python scripts/pull_indicators.py --full
```

This produces Wikipedia evidence and raw DNB-linked secondary-record evidence. It does not reproduce the manual Goodreads checks, prize verification, or the later grouping of DNB editions and formats.

## Main descriptive result

The popularity indicators agree strongly with one another in this sample. Literary prize counts show a moderate relationship with the popularity indicators, while DNB-linked secondary records show a weaker and less consistent relationship. These correlations are descriptive because the corpus is small and several prestige values are missing.

## Data sources

- Deutsche Nationalbibliothek (DNB) catalogue and SRU service
- Wikidata
- German Wikipedia and Wikimedia pageview data
- Goodreads, collected through manual author and title checks
- Official prize organisations, publishers, and authors' official websites for prize verification

Values were collected in September 2026. Individual retrieval dates, source URLs, evidence notes, and missing-data decisions are recorded in the workbooks.

## AI-use disclosure

Python scripts and provisional data cleaning suggestions were substantially developed with help of AI. I made the final decisions about the operational criteria, manually checked ambiguous DNB records and external sources, reviewed and corrected the suggested classifications, ran the scripts, and verified their outputs. I developed the interpretation myself, partly through guided discussion with AI. The project report text is my own; AI was used for factual consistency and clarity checks on my own writing.

## Reuse note

The repository contains bibliographic metadata and derived indicator values, not the copyrighted literary texts or academic articles consulted during verification. Source providers may apply their own reuse conditions. No licence for the repository has been selected yet.
