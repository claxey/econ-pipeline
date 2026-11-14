"""Fetch recent headlines for an indicator and country from Google News RSS (no API key).

Headlines are untrusted text from the internet: links are limited to http/https and titles
are cleaned before the dashboard shows them.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests
from defusedxml import ElementTree as ET

from pipeline.notes import COUNTRY_NAMES, TOPIC_QUERIES

RSS = "https://news.google.com/rss/search?q={q}&hl=en&gl=US&ceid=US:en"
HEADERS = {"User-Agent": "econ-indicator-pipeline/1.0"}


def build_query(source_id, country, days=30):
    name = COUNTRY_NAMES.get(country, country)
    topic = TOPIC_QUERIES.get(source_id, source_id.replace("_", " "))
    return f"{name} {topic} when:{days}d"


def clean_title(title, publisher=""):
    title = re.sub(r"[\[\]\r\n]+", " ", title or "").strip()
    if publisher and title.endswith(f" - {publisher}"):
        title = title[: -len(publisher) - 3].rstrip()
    return re.sub(r"\s+", " ", title)


def parse_rss(xml_text, limit=5):
    root = ET.fromstring(xml_text)
    seen, items = set(), []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        if not link.lower().startswith(("http://", "https://")):
            continue
        publisher = (item.findtext("source") or "").strip()
        title = clean_title(item.findtext("title"), publisher)
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        try:
            published = parsedate_to_datetime(item.findtext("pubDate"))
        except (TypeError, ValueError):
            published = None
        items.append({"title": title, "publisher": publisher, "published": published, "link": link})
    items.sort(key=lambda a: a["published"].timestamp() if a["published"] else 0, reverse=True)
    return items[:limit]


def fetch_headlines(source_id, country, limit=5, session=None):
    session = session or requests.Session()
    url = RSS.format(q=quote(build_query(source_id, country)))
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return parse_rss(resp.text, limit)


def fetch_for(source_id, countries, limit=5, session=None, max_workers=4):
    """Fetch headlines for several countries at the same time. Returns (articles, errors) by country."""
    def work(country):
        try:
            return country, fetch_headlines(source_id, country, limit, session), None
        except Exception as exc:
            return country, [], str(exc)[:150]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(work, countries))
    return ({c: a for c, a, _ in results}, {c: e for c, _, e in results if e})
