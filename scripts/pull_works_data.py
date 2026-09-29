#!/usr/bin/env python3
"""Pull the first DNB/Wikidata dataset for the frozen 18-author corpus.

The script keeps three grains separate:

1. DNB raw records: one row per catalogue record.
2. Work candidates: automated title groups that still require manual review.
3. Wikidata authors: one row per frozen author.

No DNB record count is treated as a count of distinct works. Missing metadata is
left blank; it is never converted to a real-world zero.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


INPUT_PATH = Path("data/author_catalog_coverage.csv")
RAW_OUTPUT_PATH = Path("data/dnb_records_first_pull.csv")
WORK_OUTPUT_PATH = Path("data/dnb_work_candidates_first_pull.csv")
WIKIDATA_OUTPUT_PATH = Path("data/wikidata_authors_first_pull.csv")
QUALITY_OUTPUT_PATH = Path("data/works_first_pull_quality.csv")
JSON_OUTPUT_PATH = Path("data/works_first_pull.json")

DNB_ENDPOINT = "https://services.dnb.de/sru/dnb"
WIKIDATA_ENTITY_ENDPOINT = "https://www.wikidata.org/wiki/Special:EntityData"
WIKIDATA_API_ENDPOINT = "https://www.wikidata.org/w/api.php"
DEWIKI_API_ENDPOINT = "https://de.wikipedia.org/w/api.php"
USER_AGENT = "TU-Darmstadt-student-project/1.0"
PULL_TIMESTAMP = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

FROZEN_AUTHORS = (
    "Navid Kermani",
    "Nava Ebrahimi",
    "Shida Bazyar",
    "SAID",
    "Nassir Djafari",
    "Sudabeh Mohafez",
    "Cyrus Atabay",
    "Mehrnousch Zaeri-Esfahani",
    "Fahimeh Farsaie",
    "Behzad Karim Khani",
    "Shirin Kumm",
    "Noshin Shahrokhi",
    "Shani Katayun",
    "Nasrin Siege",
    "Amir Gudarzi",
    "Hengameh Yaghoobifarah",
    "May Atashkar",
    "Asal Dardan",
)

SRU_NAMESPACE = "{http://www.loc.gov/zing/srw/}"
DC_NAMESPACE = "{http://purl.org/dc/elements/1.1/}"


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise
            time.sleep((1, 3, 7)[attempt])
    raise RuntimeError("JSON request failed without an HTTP response")


def fetch_xml(url: str) -> ET.Element:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        return ET.fromstring(response.read())


def join_values(values: list[str]) -> str:
    return " | ".join(dict.fromkeys(value.strip() for value in values if value.strip()))


def first_four_digit_year(values: list[str]) -> int | None:
    years: list[int] = []
    for value in values:
        years.extend(int(match) for match in re.findall(r"(?<!\d)(1[5-9]\d{2}|20\d{2})(?!\d)", value))
    return min(years) if years else None


def title_core(title: str) -> str:
    """Remove only the responsibility statement; preserve subtitles/edition clues."""
    return re.split(r"\s+/\s+", title.strip(), maxsplit=1)[0].strip(" .")


def normalize_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title_core(title)).casefold()
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")


def dnb_query_for_author(author: dict[str, str]) -> tuple[str, str]:
    if author.get("gnd_id"):
        return f"aunidref={author['gnd_id']}", "GND-linked author records"
    if author.get("dnb_title"):
        return f'tit="{author["dnb_title"]}"', "verified title fallback"
    return f'atr="{author["dnb_name"]}"', "exact displayed author name"


def dnb_url(query: str, start_record: int) -> str:
    params = {
        "version": "1.1",
        "operation": "searchRetrieve",
        "query": query,
        "recordSchema": "oai_dc",
        "maximumRecords": "100",
        "startRecord": str(start_record),
    }
    return f"{DNB_ENDPOINT}?{urllib.parse.urlencode(params)}"


def dc_values(record: ET.Element, tag: str) -> list[str]:
    return [element.text or "" for element in record.findall(f".//{DC_NAMESPACE}{tag}")]


def identifier_values(record: ET.Element, identifier_type: str) -> list[str]:
    values: list[str] = []
    for identifier in record.findall(f".//{DC_NAMESPACE}identifier"):
        type_value = next(
            (value for key, value in identifier.attrib.items() if key.endswith("type")),
            "",
        )
        if type_value.endswith(identifier_type):
            values.append(identifier.text or "")
    return values


def parse_dnb_record(
    author_name: str,
    query: str,
    query_method: str,
    query_url: str,
    record: ET.Element,
) -> dict[str, object]:
    titles = dc_values(record, "title")
    dates = dc_values(record, "date")
    creators = dc_values(record, "creator")
    contributors = dc_values(record, "contributor")
    publishers = dc_values(record, "publisher")
    languages = dc_values(record, "language")
    subjects = dc_values(record, "subject")
    formats = dc_values(record, "format")
    types = dc_values(record, "type")
    idns = identifier_values(record, "IDN")
    isbns = identifier_values(record, "ISBN")
    title = titles[0] if titles else ""
    position = record.findtext(f"{SRU_NAMESPACE}recordPosition", default="")
    return {
        "author_name": author_name,
        "query_method": query_method,
        "query_expression": query,
        "query_url": query_url,
        "record_position": position,
        "dnb_idn": idns[0] if idns else "",
        "record_url": f"https://d-nb.info/{idns[0]}" if idns else "",
        "title_raw": title,
        "title_core": title_core(title),
        "title_normalized": normalize_title(title),
        "publication_date_raw": join_values(dates),
        "publication_year": first_four_digit_year(dates) or "",
        "publishers": join_values(publishers),
        "languages": join_values(languages),
        "subjects": join_values(subjects),
        "formats": join_values(formats),
        "resource_types": join_values(types),
        "creators": join_values(creators),
        "contributors": join_values(contributors),
        "creator_count": len([value for value in creators if value.strip()]),
        "isbns": join_values(isbns),
        "german_language_record": 1 if "ger" in languages else 0,
        "dnb_literary_subject_record": 1
        if any(subject.startswith("B ") or subject.startswith("830 ") for subject in subjects)
        else 0,
        "retrieved_at_utc": PULL_TIMESTAMP,
    }


def pull_dnb_records(author: dict[str, str]) -> tuple[list[dict[str, object]], int, str]:
    query, query_method = dnb_query_for_author(author)
    first_url = dnb_url(query, 1)
    first_root = fetch_xml(first_url)
    total = int(first_root.findtext(f"{SRU_NAMESPACE}numberOfRecords", default="0"))
    roots = [first_root]
    for start_record in range(101, total + 1, 100):
        time.sleep(0.2)
        roots.append(fetch_xml(dnb_url(query, start_record)))

    rows: list[dict[str, object]] = []
    for root in roots:
        for record in root.findall(f".//{SRU_NAMESPACE}record"):
            rows.append(
                parse_dnb_record(
                    author["author_name"],
                    query,
                    query_method,
                    first_url,
                    record,
                )
            )
    return rows, total, query_method


def preliminary_unit_type(title: str, creator_count: int) -> str:
    if re.search(r"\b(anthologie|anthology|reader|sammelband|jahrbuch|almanach)\b", title.casefold()):
        return "possible anthology or collection"
    if creator_count > 1:
        return "multi-author record"
    return "possible standalone work"


def build_work_candidates(raw_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in raw_rows:
        normalized = str(row["title_normalized"])
        group_key = normalized or f"missing-title-{row['dnb_idn'] or row['record_position']}"
        groups[(str(row["author_name"]), group_key)].append(row)

    candidates: list[dict[str, object]] = []
    for (author_name, normalized), rows in groups.items():
        core_titles = [str(row["title_core"]) for row in rows if row["title_core"]]
        title_counts = Counter(core_titles)
        canonical_title = ""
        if title_counts:
            canonical_title = sorted(
                title_counts,
                key=lambda value: (-title_counts[value], len(value), value.casefold()),
            )[0]
        years = [int(row["publication_year"]) for row in rows if row["publication_year"] != ""]
        candidate_hash = hashlib.sha1(f"{author_name}|{normalized}".encode("utf-8")).hexdigest()[:10]
        max_creator_count = max(int(row["creator_count"]) for row in rows)
        candidates.append(
            {
                "author_name": author_name,
                "work_candidate_id": f"{slug(author_name)[:24]}-{candidate_hash}",
                "canonical_title_provisional": canonical_title,
                "title_normalized_group_key": normalized,
                "earliest_year": min(years) if years else "",
                "latest_year": max(years) if years else "",
                "dnb_record_count": len(rows),
                "german_language_record_count": sum(int(row["german_language_record"]) for row in rows),
                "dnb_literary_subject_record_count": sum(
                    int(row["dnb_literary_subject_record"]) for row in rows
                ),
                "unit_type_preliminary": preliminary_unit_type(canonical_title, max_creator_count),
                "unit_type_final": "",
                "distinct_work_status": "provisional title group; manual deduplication required",
                "manual_review_status": "unreviewed",
                "dnb_idns": join_values([str(row["dnb_idn"]) for row in rows]),
                "languages": join_values([str(row["languages"]) for row in rows]),
                "subjects": join_values([str(row["subjects"]) for row in rows]),
                "resource_types": join_values([str(row["resource_types"]) for row in rows]),
                "publishers": join_values([str(row["publishers"]) for row in rows]),
                "isbns": join_values([str(row["isbns"]) for row in rows]),
                "retrieved_at_utc": PULL_TIMESTAMP,
            }
        )
    return sorted(
        candidates,
        key=lambda row: (
            FROZEN_AUTHORS.index(str(row["author_name"])),
            str(row["canonical_title_provisional"]).casefold(),
        ),
    )


def claim_entity_ids(entity: dict, property_id: str) -> list[str]:
    values: list[str] = []
    for claim in entity.get("claims", {}).get(property_id, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            values.append(value["id"])
    return list(dict.fromkeys(values))


def claim_times(entity: dict, property_id: str) -> list[str]:
    values: list[str] = []
    for claim in entity.get("claims", {}).get(property_id, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("time"):
            values.append(value["time"])
    return list(dict.fromkeys(values))


def preferred_text(mapping: dict) -> str:
    for language in ("de", "en"):
        value = mapping.get(language, {}).get("value")
        if value:
            return value
    return ""


def resolve_entity_labels(entity_ids: set[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    ordered_ids = sorted(entity_ids)
    for start in range(0, len(ordered_ids), 50):
        batch = ordered_ids[start : start + 50]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "labels",
            "languages": "de|en",
            "format": "json",
        }
        url = f"{WIKIDATA_API_ENDPOINT}?{urllib.parse.urlencode(params)}"
        result = fetch_json(url)
        for entity_id, entity in result.get("entities", {}).items():
            labels[entity_id] = preferred_text(entity.get("labels", {})) or entity_id
        time.sleep(0.2)
    return labels


def dewiki_page_info_batch(titles: list[str]) -> dict[str, tuple[object, object, str, str]]:
    if not titles:
        return {}
    params = {
        "action": "query",
        "prop": "info",
        "titles": "|".join(titles),
        "format": "json",
        "formatversion": "2",
    }
    url = f"{DEWIKI_API_ENDPOINT}?{urllib.parse.urlencode(params)}"
    result = fetch_json(url)
    pages = result.get("query", {}).get("pages", [])
    page_info: dict[str, tuple[object, object, str, str]] = {}
    for page in pages:
        if page.get("missing"):
            page_info[page.get("title", "")] = ("", "", url, "missing page")
        else:
            page_info[page.get("title", "")] = (
                page.get("length", ""),
                page.get("lastrevid", ""),
                url,
                "retrieved",
            )
    return page_info


def pull_wikidata_rows(authors: list[dict[str, str]]) -> list[dict[str, object]]:
    qids = [author.get("wikidata_candidate_id", "") for author in authors]
    verified_qids = [qid for qid in qids if qid]
    params = {
        "action": "wbgetentities",
        "ids": "|".join(verified_qids),
        "props": "labels|descriptions|claims|sitelinks",
        "languages": "de|en",
        "format": "json",
    }
    entity_api_url = f"{WIKIDATA_API_ENDPOINT}?{urllib.parse.urlencode(params)}"
    entities = fetch_json(entity_api_url).get("entities", {}) if verified_qids else {}
    dewiki_titles = [
        entity.get("sitelinks", {}).get("dewiki", {}).get("title", "")
        for entity in entities.values()
    ]
    page_info = dewiki_page_info_batch([title for title in dewiki_titles if title])

    staged: list[dict[str, object]] = []
    referenced_ids: set[str] = set()
    for author in authors:
        qid = author.get("wikidata_candidate_id", "")
        if not qid:
            staged.append(
                {
                    "author_name": author["author_name"],
                    "wikidata_id": "",
                    "metadata_status": "missing: no verified Wikidata item in the audit",
                    "retrieved_at_utc": PULL_TIMESTAMP,
                }
            )
            continue

        entity_url = f"https://www.wikidata.org/wiki/{qid}"
        entity = entities[qid]
        award_ids = claim_entity_ids(entity, "P166")
        birth_place_ids = claim_entity_ids(entity, "P19")
        notable_work_ids = claim_entity_ids(entity, "P800")
        referenced_ids.update(award_ids + birth_place_ids + notable_work_ids)
        dewiki_title = entity.get("sitelinks", {}).get("dewiki", {}).get("title", "")
        page_length: object = ""
        page_revision: object = ""
        page_url = ""
        page_status = "no German Wikipedia sitelink"
        if dewiki_title:
            page_length, page_revision, page_url, page_status = page_info.get(
                dewiki_title,
                ("", "", "", "page missing from batched response"),
            )
        staged.append(
            {
                "author_name": author["author_name"],
                "wikidata_id": qid,
                "wikidata_label": preferred_text(entity.get("labels", {})),
                "wikidata_description": preferred_text(entity.get("descriptions", {})),
                "birth_date_wikidata": join_values(claim_times(entity, "P569")),
                "birth_place_ids": join_values(birth_place_ids),
                "award_statement_count": len(award_ids),
                "award_ids": join_values(award_ids),
                "notable_work_statement_count": len(notable_work_ids),
                "notable_work_ids": join_values(notable_work_ids),
                "dewiki_title": dewiki_title,
                "dewiki_page_exists": 1 if dewiki_title else 0,
                "dewiki_page_length_bytes": page_length,
                "dewiki_last_revision_id": page_revision,
                "dewiki_api_url": page_url,
                "dewiki_status": page_status,
                "entity_url": entity_url,
                "entity_api_url": entity_api_url,
                "metadata_status": "retrieved",
                "retrieved_at_utc": PULL_TIMESTAMP,
            }
        )

    labels = resolve_entity_labels(referenced_ids)
    for row in staged:
        birth_ids = str(row.get("birth_place_ids", "")).split(" | ") if row.get("birth_place_ids") else []
        award_ids = str(row.get("award_ids", "")).split(" | ") if row.get("award_ids") else []
        notable_ids = str(row.get("notable_work_ids", "")).split(" | ") if row.get("notable_work_ids") else []
        row["birth_place_labels"] = join_values([labels.get(entity_id, entity_id) for entity_id in birth_ids])
        row["award_labels"] = join_values([labels.get(entity_id, entity_id) for entity_id in award_ids])
        row["notable_work_labels"] = join_values([labels.get(entity_id, entity_id) for entity_id in notable_ids])
    return staged


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_quality_rows(
    authors: list[dict[str, str]],
    raw_rows: list[dict[str, object]],
    candidates: list[dict[str, object]],
    wikidata_rows: list[dict[str, object]],
    expected_counts: dict[str, int],
    fetched_counts: dict[str, int],
    pull_errors: list[str],
) -> list[dict[str, object]]:
    nonblank_idns = [
        (str(row["author_name"]), str(row["dnb_idn"]))
        for row in raw_rows
        if row["dnb_idn"]
    ]
    duplicate_author_idns = len(nonblank_idns) - len(set(nonblank_idns))
    mismatch_authors = [
        name
        for name in FROZEN_AUTHORS
        if expected_counts.get(name) != fetched_counts.get(name)
    ]
    metrics = [
        ("frozen_author_count", len(authors), "expected 18"),
        ("raw_dnb_record_count", len(raw_rows), "one row per DNB catalogue record"),
        ("provisional_work_candidate_count", len(candidates), "automated title groups; not confirmed works"),
        ("authors_with_zero_dnb_records", sum(fetched_counts.get(name, 0) == 0 for name in FROZEN_AUTHORS), "must be investigated if nonzero"),
        ("raw_records_missing_dnb_idn", sum(not row["dnb_idn"] for row in raw_rows), "blank is preserved"),
        ("raw_records_missing_title", sum(not row["title_raw"] for row in raw_rows), "blank is preserved"),
        ("raw_records_missing_year", sum(row["publication_year"] == "" for row in raw_rows), "blank is preserved"),
        ("duplicate_author_idn_rows", duplicate_author_idns, "should be zero after pagination"),
        ("authors_with_count_mismatch", len(mismatch_authors), join_values(mismatch_authors)),
        ("work_candidates_requiring_manual_review", sum(row["manual_review_status"] == "unreviewed" for row in candidates), "expected: every provisional group"),
        ("authors_without_verified_wikidata_item", sum(not row.get("wikidata_id") for row in wikidata_rows), "missing, not zero"),
        ("api_pull_error_count", len(pull_errors), join_values(pull_errors)),
    ]
    return [
        {
            "check": check,
            "value": value,
            "interpretation": interpretation,
            "checked_at_utc": PULL_TIMESTAMP,
        }
        for check, value, interpretation in metrics
    ]


def main() -> None:
    with INPUT_PATH.open(encoding="utf-8") as handle:
        coverage_rows = list(csv.DictReader(handle))
    by_name = {row["author_name"]: row for row in coverage_rows}
    missing_authors = [name for name in FROZEN_AUTHORS if name not in by_name]
    if missing_authors:
        raise ValueError(f"Frozen authors missing from coverage input: {missing_authors}")
    authors = [by_name[name] for name in FROZEN_AUTHORS]

    raw_rows: list[dict[str, object]] = []
    expected_counts: dict[str, int] = {}
    fetched_counts: dict[str, int] = {}
    pull_errors: list[str] = []
    for author in authors:
        name = author["author_name"]
        expected_counts[name] = int(author["dnb_raw_record_count"])
        try:
            rows, total, method = pull_dnb_records(author)
            raw_rows.extend(rows)
            fetched_counts[name] = len(rows)
            if len(rows) != total:
                pull_errors.append(f"{name}: parsed {len(rows)} of {total} DNB records")
            print(f"DNB {name}: {len(rows)} records ({method})")
        except Exception as error:
            fetched_counts[name] = 0
            pull_errors.append(f"{name}: {type(error).__name__}: {error}")
        time.sleep(0.25)

    candidates = build_work_candidates(raw_rows)
    try:
        wikidata_rows = pull_wikidata_rows(authors)
    except Exception as error:
        pull_errors.append(f"Wikidata pull: {type(error).__name__}: {error}")
        wikidata_rows = [
            {
                "author_name": author["author_name"],
                "metadata_status": f"pull failed: {type(error).__name__}",
                "retrieved_at_utc": PULL_TIMESTAMP,
            }
            for author in authors
        ]

    quality_rows = build_quality_rows(
        authors,
        raw_rows,
        candidates,
        wikidata_rows,
        expected_counts,
        fetched_counts,
        pull_errors,
    )

    write_csv(RAW_OUTPUT_PATH, raw_rows)
    write_csv(WORK_OUTPUT_PATH, candidates)
    write_csv(WIKIDATA_OUTPUT_PATH, wikidata_rows)
    write_csv(QUALITY_OUTPUT_PATH, quality_rows)
    JSON_OUTPUT_PATH.write_text(
        json.dumps(
            {
                "pull_timestamp_utc": PULL_TIMESTAMP,
                "frozen_authors": list(FROZEN_AUTHORS),
                "raw_records": raw_rows,
                "work_candidates": candidates,
                "wikidata_authors": wikidata_rows,
                "quality_checks": quality_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"Saved {len(raw_rows)} raw DNB records, {len(candidates)} provisional "
        f"work candidates, and {len(wikidata_rows)} Wikidata author rows."
    )


if __name__ == "__main__":
    main()
