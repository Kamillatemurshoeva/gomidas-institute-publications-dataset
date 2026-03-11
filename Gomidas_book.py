#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.gomidas.org"
CATALOG_URL = f"{BASE_URL}/books"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}

TIMEOUT = 30
DELAY = 0.35


@dataclass
class Record:
    title: str = ""
    date_or_period: str = ""
    author_or_creator: str = ""
    description_or_abstract: str = ""
    url_to_original_object: str = ""
    object_type: str = "publication"


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    parsed = parsed._replace(query="", fragment="")
    return urlunparse(parsed)


def extract_year(text: str) -> str:
    text = clean_text(text)
    m = re.search(r"\b(1[89]\d{2}|20\d{2}|21\d{2})\b", text)
    return m.group(1) if m else ""


def fetch_response(url: str, session: requests.Session) -> requests.Response:
    r = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    time.sleep(DELAY)
    return r


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def get_meta(soup: BeautifulSoup, attr_name: str, attr_value: str) -> str:
    tag = soup.find("meta", attrs={attr_name: attr_value})
    if tag and tag.get("content"):
        return clean_text(tag["content"])
    return ""


def remove_site_suffix(title: str) -> str:
    title = clean_text(title)
    title = re.sub(r"\s*\|\s*Gomidas Institute.*$", "", title, flags=re.I)
    title = re.sub(r"\s*-\s*Gomidas Institute.*$", "", title, flags=re.I)
    return clean_text(title)


def extract_id_from_url(url: str) -> Optional[int]:
    m = re.search(r"/books/show/(\d+)$", normalize_url(url))
    return int(m.group(1)) if m else None


def collect_catalog_pages(session: requests.Session) -> List[str]:
    """
    Collect /books plus paginated catalog pages if pagination exists.
    """
    to_visit = [CATALOG_URL]
    seen = set()
    pages = []

    while to_visit:
        url = to_visit.pop(0)
        url = normalize_url(url)
        if url in seen:
            continue
        seen.add(url)

        resp = fetch_response(url, session)
        final_url = normalize_url(resp.url)
        soup = make_soup(resp.text)
        pages.append(final_url)

        for a in soup.find_all("a", href=True):
            href = urljoin(BASE_URL, a["href"])
            href = normalize_url(href)
            # keep only /books and paginated /books pages, not detail pages here
            if re.search(r"/books(?:/)?$", href) or re.search(r"/books\?page=\d+$", href):
                if href not in seen and href not in to_visit:
                    to_visit.append(href)

    return pages


def collect_detail_links_from_page(soup: BeautifulSoup) -> List[str]:
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, a["href"])
        href = normalize_url(href)
        if re.search(r"/books/show/\d+$", href):
            if href not in seen:
                seen.add(href)
                links.append(href)
    return links


def collect_all_detail_links(session: requests.Session) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    catalog_pages = collect_catalog_pages(session)
    all_links = set()
    listing_hints: Dict[str, Dict[str, str]] = {}

    for page_url in catalog_pages:
        resp = fetch_response(page_url, session)
        soup = make_soup(resp.text)

        page_links = collect_detail_links_from_page(soup)
        for link in page_links:
            all_links.add(link)

        page_hints = parse_listing_hints(soup)
        listing_hints.update(page_hints)

    ordered = sorted(all_links, key=lambda x: extract_id_from_url(x) or 0)
    return ordered, listing_hints


def parse_listing_hints(soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
    hints: Dict[str, Dict[str, str]] = {}

    for a in soup.find_all("a", href=True):
        href = normalize_url(urljoin(BASE_URL, a["href"]))
        if not re.search(r"/books/show/\d+$", href):
            continue

        parent_text = clean_text(a.parent.get_text(" ", strip=True)) if a.parent else ""

        title = ""
        author = ""
        year = extract_year(parent_text)

        m = re.search(
            r"(?P<author>.+?),\s+(?P<title>.+?),\s+London\s*:?\s+Gomidas Institute,\s+(?P<year>\d{4})",
            parent_text,
            flags=re.I,
        )
        if m:
            author = clean_text(m.group("author"))
            title = clean_text(m.group("title"))
            year = clean_text(m.group("year"))

        hints[href] = {
            "title": title,
            "author_or_creator": author,
            "date_or_period": year,
        }

    return hints


def is_noise_line(text: str) -> bool:
    low = text.lower().strip()

    patterns = [
        r"^isbn\b",
        r"^price:",
        r"^uk£",
        r"^us\$",
        r"^aud\$",
        r"^to order please contact",
        r"^books and publications$",
        r"^view books by categories",
        r"^«?\s*back to books listing",
        r"^contact and mailing list$",
        r"^follow us",
        r"^facebook$",
        r"^youtube$",
        r"^x$",
        r"^about$",
        r"^projects and studies$",
        r"^campaigns$",
        r"^events$",
        r"^video$",
        r"^press$",
        r"^books$",
        r"^publications$",
        r"^blog$",
        r"^gomidas institute$",
        r"^\d+\s*pp\b",
        r"\bpaperback\b",
        r"\bhardback\b",
        r"\bmaps?\b",
        r"\billustrations?\b",
        r"\bphotos?\b",
        r"\bindex\b",
        r"^london\s*:",
        r"^copyright",
    ]
    return any(re.search(p, low, flags=re.I) for p in patterns)


def is_probable_catalog_page(soup: BeautifulSoup, final_url: str, title: str) -> bool:
    final_url = normalize_url(final_url)
    if re.search(r"/books/?$", final_url):
        return True
    if title.lower() == "books and publications":
        return True
    return False


def extract_author_from_detail(soup: BeautifulSoup, title: str, page_text: str) -> str:
    h1 = soup.find("h1")
    if h1:
        lines = []
        for el in h1.find_all_next(limit=15):
            if isinstance(el, Tag):
                txt = clean_text(el.get_text(" ", strip=True))
                if txt:
                    lines.append(txt)

        for line in lines:
            low = line.lower()
            if line == title:
                continue
            if is_noise_line(line):
                continue
            if "back to books listing" in low:
                continue
            if len(line) > 180:
                continue
            return line

    if title:
        m = re.search(
            rf"(?P<author>.+?),\s+{re.escape(title)},\s+.*?\b(1[89]\d{{2}}|20\d{{2}}|21\d{{2}})\b",
            page_text,
            flags=re.I,
        )
        if m:
            return clean_text(m.group("author"))

    return ""


def extract_description_from_detail(soup: BeautifulSoup, title: str) -> str:
    h1 = soup.find("h1")
    if not h1:
        return ""

    title_text = clean_text(title or h1.get_text(" ", strip=True))
    blocks: List[str] = []

    for el in h1.find_all_next():
        if not isinstance(el, Tag):
            continue
        if el.name not in {"p", "div", "span", "li"}:
            continue

        txt = clean_text(el.get_text(" ", strip=True))
        if not txt:
            continue
        if txt == title_text:
            continue

        low = txt.lower()
        if "back to books listing" in low:
            break
        if is_noise_line(txt):
            continue

        if len(txt) >= 12:
            blocks.append(txt)

    seen = set()
    unique = []
    for b in blocks:
        if b not in seen:
            seen.add(b)
            unique.append(b)

    desc = clean_text(" ".join(unique))

    desc = re.sub(r"«?\s*Back to books listing.*$", "", desc, flags=re.I)
    desc = re.sub(r"View books by categories.*$", "", desc, flags=re.I)
    return clean_text(desc)


def parse_detail_page(url: str, session: requests.Session) -> Optional[Record]:
    try:
        response = fetch_response(url, session)
    except requests.HTTPError as e:
        if getattr(e.response, "status_code", None) == 404:
            return None
        raise

    final_url = normalize_url(response.url)

    if not re.search(r"/books/show/\d+$", final_url):
        return None

    soup = make_soup(response.text)

    title = (
        get_meta(soup, "property", "og:title")
        or (clean_text(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else "")
        or (clean_text(soup.title.get_text(" ", strip=True)) if soup.title else "")
    )
    title = remove_site_suffix(title)

    if not title:
        return None

    if is_probable_catalog_page(soup, final_url, title):
        return None

    page_text = clean_text(soup.get_text(" ", strip=True))
    date_or_period = extract_year(page_text)
    author = extract_author_from_detail(soup, title, page_text)
    description = extract_description_from_detail(soup, title)

    if not description:
        meta_desc = get_meta(soup, "property", "og:description") or get_meta(soup, "name", "description")
        if meta_desc and len(meta_desc) > 20:
            description = meta_desc

    return Record(
        title=title,
        date_or_period=date_or_period,
        author_or_creator=clean_text(author),
        description_or_abstract=clean_text(description),
        url_to_original_object=final_url,
        object_type="publication",
    )


def merge_with_hint(record: Record, hint: Dict[str, str]) -> Record:
    if not record.title:
        record.title = hint.get("title", "")
    if not record.author_or_creator:
        record.author_or_creator = hint.get("author_or_creator", "")
    if not record.date_or_period:
        record.date_or_period = hint.get("date_or_period", "")
    return record


def normalize_title(text: str) -> str:
    text = remove_site_suffix(text)
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("–", "-")
    return clean_text(text)


def normalize_author(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"^(by|author:)\s+", "", text, flags=re.I)
    return text.strip(" ,;:-")


def normalize_description(text: str) -> str:
    text = clean_text(text)
    if not text:
        return ""
    text = re.sub(r"«?\s*Back to books listing.*$", "", text, flags=re.I)
    text = re.sub(r"View books by categories.*$", "", text, flags=re.I)
    text = re.sub(r"\bto order please contact\b.*$", "", text, flags=re.I)
    return clean_text(text)


def clean_record(r: Record) -> Record:
    return Record(
        title=normalize_title(r.title),
        date_or_period=extract_year(r.date_or_period),
        author_or_creator=normalize_author(r.author_or_creator),
        description_or_abstract=normalize_description(r.description_or_abstract),
        url_to_original_object=normalize_url(r.url_to_original_object),
        object_type="publication",
    )


def dedupe_records(records: List[Record]) -> List[Record]:
    seen = set()
    out = []
    for r in records:
        key = r.url_to_original_object.lower() if r.url_to_original_object else (
            r.title.lower(),
            r.author_or_creator.lower(),
            r.date_or_period.lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def save_csv(records: List[Record], path: str) -> None:
    fieldnames = [
        "title",
        "date_or_period",
        "author_or_creator",
        "description_or_abstract",
        "url_to_original_object",
        "object_type",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))


def save_jsonl(records: List[Record], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def main() -> None:
    session = requests.Session()

    detail_links, listing_hints = collect_all_detail_links(session)
    print(f"Found {len(detail_links)} linked detail URLs")

    raw_records: List[Record] = []

    for i, url in enumerate(detail_links, start=1):
        try:
            record = parse_detail_page(url, session)
            if record is None:
                print(f"[{i}/{len(detail_links)}] SKIP - {url}")
                continue

            record = merge_with_hint(record, listing_hints.get(url, {}))
            raw_records.append(record)
            print(f"[{i}/{len(detail_links)}] OK - {record.title}")
        except Exception as e:
            print(f"[{i}/{len(detail_links)}] ERROR - {url} - {e}")

    raw_records = dedupe_records(raw_records)
    clean_records = [clean_record(r) for r in raw_records]
    clean_records = dedupe_records(clean_records)

    # extra safety: drop obvious catalog-page accidents
    clean_records = [
        r for r in clean_records
        if r.title.lower() != "books and publications"
        and re.search(r"/books/show/\d+$", r.url_to_original_object)
    ]

    save_csv(clean_records, "gomidas_books_clean.csv")
    save_jsonl(clean_records, "gomidas_books_clean.jsonl")

    print(f"\nSaved clean records: {len(clean_records)}")
    missing_desc = sum(1 for r in clean_records if not r.description_or_abstract)
    print(f"Records without description: {missing_desc}")


if __name__ == "__main__":
    main()