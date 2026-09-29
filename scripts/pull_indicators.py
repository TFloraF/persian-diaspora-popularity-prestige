#!/usr/bin/env python3
"""Pull the reproducible Wikipedia and DNB indicators.

Sources:
- German Wikipedia Action API: article existence, current byte length, revisions.
- Wikimedia pageviews API: daily article views for a fixed twelve-month period.
- DNB SRU: title records linked to an author through the intellectual subject
  GND index (swnidref). Records crediting the person in any MARC 100/700 role
  are kept in the raw output but excluded from the secondary-record count.

The script preserves missing values. It writes raw evidence and one compact
summary; it does not calculate popularity or prestige scores. Run it with
``--full`` to process the frozen 18-author corpus. Without that option, it
runs the original three-author pilot.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "step3_pilot"
OUT.mkdir(parents=True, exist_ok=True)

USER_AGENT = "TU-Darmstadt-DDS-student-project/1.0 (metadata pilot; contact via course supervisor)"
PV_START = "20250901"
PV_END = "20260831"

PILOT_AUTHORS = [
    {
        "author": "Navid Kermani",
        "qid": "Q99728",
        "gnd": "121162680",
        "dewiki_title": "Navid Kermani",
    },
    {
        "author": "Nava Ebrahimi",
        "qid": "Q42844801",
        "gnd": "173913873",
        "dewiki_title": "Nava Ebrahimi",
    },
    {
        "author": "Noshin Shahrokhi",
        "qid": None,
        "gnd": None,
        "dewiki_title": None,
    },
]


def load_full_authors() -> list[dict]:
    """Load the frozen 18-author corpus from the audited catalogue table."""
    authors: list[dict] = []
    with (ROOT / "data" / "author_catalog_coverage.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            if row["author_name"] == "Bahman Nirumand":
                continue
            authors.append(
                {
                    "author": row["author_name"],
                    "qid": row["wikidata_id"] or None,
                    "gnd": row["gnd_id"] or None,
                    "dewiki_title": row["dewiki_title"] or None,
                }
            )
    if len(authors) != 18:
        raise ValueError(f"Expected frozen corpus of 18 authors, found {len(authors)}")
    return authors


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch(url: str, *, attempts: int = 6) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read()
                time.sleep(0.4)
                return payload
        except urllib.error.HTTPError as exc:
            error = exc
            if exc.code == 429 and attempt + 1 < attempts:
                retry_after = exc.headers.get("Retry-After", "")
                wait_seconds = int(retry_after) if retry_after.isdigit() else 15 * (attempt + 1)
                time.sleep(wait_seconds)
                continue
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
        except Exception as exc:  # pragma: no cover - network retry
            error = exc
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
    assert error is not None
    raise error


def json_get(base: str, params: dict[str, str]) -> tuple[dict, str]:
    url = base + "?" + urllib.parse.urlencode(params)
    return json.loads(fetch(url).decode("utf-8")), url


def search_dewiki_exact(name: str) -> tuple[list[dict], str]:
    data, url = json_get(
        "https://de.wikipedia.org/w/api.php",
        {
            "action": "query",
            "list": "search",
            "srsearch": f'intitle:"{name}"',
            "srnamespace": "0",
            "srlimit": "10",
            "format": "json",
            "formatversion": "2",
        },
    )
    return data.get("query", {}).get("search", []), url


def wikipedia_page_info(title: str) -> tuple[dict, str]:
    data, url = json_get(
        "https://de.wikipedia.org/w/api.php",
        {
            "action": "query",
            "prop": "info",
            "titles": title,
            "redirects": "1",
            "inprop": "url",
            "format": "json",
            "formatversion": "2",
        },
    )
    page = data.get("query", {}).get("pages", [{}])[0]
    return page, url


def wikipedia_revision_count(title: str) -> tuple[int, list[str]]:
    count = 0
    continuation: dict[str, str] = {}
    urls: list[str] = []
    while True:
        params = {
            "action": "query",
            "prop": "revisions",
            "titles": title,
            "rvprop": "ids",
            "rvlimit": "max",
            "rvdir": "newer",
            "format": "json",
            "formatversion": "2",
        }
        params.update(continuation)
        data, url = json_get("https://de.wikipedia.org/w/api.php", params)
        urls.append(url)
        page = data.get("query", {}).get("pages", [{}])[0]
        count += len(page.get("revisions", []))
        if "continue" not in data:
            break
        continuation = {
            key: str(value)
            for key, value in data["continue"].items()
            if key != "continue"
        }
    return count, urls


def wikipedia_pageviews(title: str) -> tuple[int, int, str]:
    encoded_title = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"de.wikipedia.org/all-access/user/{encoded_title}/daily/{PV_START}/{PV_END}"
    )
    data = json.loads(fetch(url).decode("utf-8"))
    items = data.get("items", [])
    return sum(int(item.get("views", 0)) for item in items), len(items), url


NS = {
    "srw": "http://www.loc.gov/zing/srw/",
    "marc": "http://www.loc.gov/MARC21/slim",
}


def marc_subfields(record: ET.Element, tag: str, code: str | None = None) -> list[str]:
    values: list[str] = []
    for field in record.findall(f"marc:datafield[@tag='{tag}']", NS):
        for subfield in field.findall("marc:subfield", NS):
            if code is None or subfield.attrib.get("code") == code:
                if subfield.text:
                    values.append(subfield.text.strip())
    return values


def dnb_subject_records(author: str, gnd: str) -> tuple[list[dict], str, int]:
    query = f"swnidref={gnd}"
    base_params = {
        "version": "1.1",
        "operation": "searchRetrieve",
        "query": query,
        "recordSchema": "MARC21-xml",
        "maximumRecords": "100",
    }
    first_url = ""
    total = 0
    output: list[dict] = []
    start_record = 1
    while start_record == 1 or start_record <= total:
        params = {**base_params, "startRecord": str(start_record)}
        url = "https://services.dnb.de/sru/dnb?" + urllib.parse.urlencode(params)
        if not first_url:
            first_url = url
        root = ET.fromstring(fetch(url))
        total = int(root.findtext("srw:numberOfRecords", default="0", namespaces=NS))
        wrappers = root.findall(".//srw:recordData", NS)
        for wrapper in wrappers:
            record = wrapper.find("marc:record", NS)
            if record is None:
                continue
            idn = ""
            control_001 = record.find("marc:controlfield[@tag='001']", NS)
            if control_001 is not None and control_001.text:
                idn = control_001.text.strip()

            title_parts = []
            for code in ("a", "b"):
                title_parts.extend(marc_subfields(record, "245", code))
            title = " : ".join(part.rstrip(" /:") for part in title_parts if part)

            credited_target = False
            target_roles: list[str] = []
            credited_names: list[str] = []
            for tag in ("100", "700"):
                for field in record.findall(f"marc:datafield[@tag='{tag}']", NS):
                    gnd_values = [
                        (sf.text or "").strip()
                        for sf in field.findall("marc:subfield[@code='0']", NS)
                    ]
                    if not any(gnd in value for value in gnd_values):
                        continue
                    credited_target = True
                    credited_names.extend(
                        (sf.text or "").strip()
                        for sf in field.findall("marc:subfield[@code='a']", NS)
                    )
                    target_roles.extend(
                        (sf.text or "").strip()
                        for code in ("e", "4")
                        for sf in field.findall(f"marc:subfield[@code='{code}']", NS)
                    )

            subjects = []
            for tag in ("600", "610", "650", "651", "653"):
                subjects.extend(marc_subfields(record, tag))

            output.append(
                {
                    "author": author,
                    "gnd": gnd,
                    "dnb_idn": idn,
                    "dnb_url": f"https://d-nb.info/{idn}" if idn else "",
                    "title": title,
                    "target_credited_100_or_700": credited_target,
                    "target_credit_names": " | ".join(dict.fromkeys(credited_names)),
                    "target_credit_roles": " | ".join(dict.fromkeys(target_roles)),
                    "subject_text": " | ".join(dict.fromkeys(subjects)),
                    "secondary_eligible": not credited_target,
                    "exclusion_reason": "target also credited as author/editor/contributor" if credited_target else "",
                    "retrieved_at_utc": now_utc(),
                    "query_url": url,
                }
            )
        if not wrappers:
            break
        start_record += len(wrappers)
    return output, first_url, total


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(authors: list[dict], out: Path, prefix: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    summary: list[dict] = []
    wiki_raw: list[dict] = []
    dnb_raw: list[dict] = []

    for author in authors:
        name = author["author"]
        row = {
            "author": name,
            "qid": author["qid"] or "",
            "gnd": author["gnd"] or "",
            "dewiki_title": author["dewiki_title"] or "",
            "dewiki_article_exists": None,
            "dewiki_length_bytes": None,
            "dewiki_revision_count": None,
            "dewiki_pageviews_2025_09_01_to_2026_08_31": None,
            "dewiki_pageview_days_returned": None,
            "dnb_subject_linked_raw_records": None,
            "dnb_subject_linked_secondary_records": None,
            "retrieved_at_utc": now_utc(),
            "notes": "",
        }

        title = author["dewiki_title"]
        search_results: list[dict] = []
        search_url = ""
        if not title:
            search_results, search_url = search_dewiki_exact(name)
            exact_titles = [
                result.get("title", "")
                for result in search_results
                if result.get("title", "").casefold() == name.casefold()
            ]
            if exact_titles:
                title = exact_titles[0]

        if title:
            page, info_url = wikipedia_page_info(title)
            exists = "missing" not in page and page.get("pageid") is not None
            row["dewiki_article_exists"] = 1 if exists else 0
            if exists:
                canonical_title = page.get("title", title)
                revisions, revision_urls = wikipedia_revision_count(canonical_title)
                views, days, views_url = wikipedia_pageviews(canonical_title)
                row["dewiki_title"] = canonical_title
                row["dewiki_length_bytes"] = int(page.get("length", 0))
                row["dewiki_revision_count"] = revisions
                row["dewiki_pageviews_2025_09_01_to_2026_08_31"] = views
                row["dewiki_pageview_days_returned"] = days
            else:
                row["dewiki_length_bytes"] = 0
                row["dewiki_revision_count"] = 0
                row["dewiki_pageviews_2025_09_01_to_2026_08_31"] = 0
                row["dewiki_pageview_days_returned"] = 0
                canonical_title = title
                revision_urls = []
                views_url = ""
            wiki_raw.append(
                {
                    "author": name,
                    "searched_title": title,
                    "canonical_title": canonical_title,
                    "article_exists": row["dewiki_article_exists"],
                    "length_bytes": row["dewiki_length_bytes"],
                    "revision_count": row["dewiki_revision_count"],
                    "pageviews": row["dewiki_pageviews_2025_09_01_to_2026_08_31"],
                    "pageview_days_returned": row["dewiki_pageview_days_returned"],
                    "search_url": search_url,
                    "info_url": info_url,
                    "revision_api_urls": " | ".join(revision_urls),
                    "pageviews_url": views_url,
                    "retrieved_at_utc": now_utc(),
                }
            )
        else:
            # The exact-title search is the defined completeness check for an
            # author article. No exact result means a real zero for Wikipedia.
            row["dewiki_article_exists"] = 0
            row["dewiki_length_bytes"] = 0
            row["dewiki_revision_count"] = 0
            row["dewiki_pageviews_2025_09_01_to_2026_08_31"] = 0
            row["dewiki_pageview_days_returned"] = 0
            row["notes"] = "No exact German Wikipedia author article in title search."
            wiki_raw.append(
                {
                    "author": name,
                    "searched_title": name,
                    "canonical_title": "",
                    "article_exists": 0,
                    "length_bytes": 0,
                    "revision_count": 0,
                    "pageviews": 0,
                    "pageview_days_returned": 0,
                    "search_url": search_url,
                    "info_url": "",
                    "revision_api_urls": "",
                    "pageviews_url": "",
                    "retrieved_at_utc": now_utc(),
                }
            )

        gnd = author["gnd"]
        if gnd:
            records, dnb_url, raw_total = dnb_subject_records(name, gnd)
            dnb_raw.extend(records)
            row["dnb_subject_linked_raw_records"] = raw_total
            row["dnb_subject_linked_secondary_records"] = sum(
                1 for record in records if record["secondary_eligible"]
            )
        else:
            row["notes"] = (row["notes"] + " No GND identifier; DNB secondary metric unavailable.").strip()

        summary.append(row)

    write_csv(out / f"{prefix}_reproducible_metrics.csv", summary)
    write_csv(out / "wikipedia_evidence.csv", wiki_raw)
    write_csv(out / "dnb_secondary_evidence.csv", dnb_raw)
    (out / f"{prefix}_reproducible_metrics.json").write_text(
        json.dumps(
            {
                "pageview_period": {"start": PV_START, "end": PV_END},
                "authors": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Pull the frozen 18-author corpus")
    args = parser.parse_args()
    if args.full:
        main(load_full_authors(), ROOT / "data" / "step3_full", "full")
    else:
        main(PILOT_AUTHORS, OUT, "pilot")
