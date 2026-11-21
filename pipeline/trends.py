"""Google Trends: what India is searching for right now.

Uses the public Trending Now RSS feed (no API key, no pytrends dependency that breaks
whenever Google changes its page). Results are cached on disk, so a Google outage or a
blocked network degrades to "yesterday's trends" or to no boost, never to a crash.

Regional feeds (IN-AP, IN-TG) are tried first for the Telugu channel so Telugu viewers
get what is trending where they live; national IN is the fallback.
"""
import json
import math
import pathlib
import re
import time
import xml.etree.ElementTree as ET

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "out" / "trends_cache.json"
CACHE_MAX_AGE = 24 * 3600
URLS = ("https://trends.google.com/trending/rss?geo={geo}",
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; shorts-engine/3.0)"}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _traffic(text):
    """'200K+' -> 200000, '2M+' -> 2000000, '' -> 0."""
    m = re.match(r"\s*([\d.,]+)\s*([KkMm]?)", text or "")
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2).lower()])


def _parse(xml_text, geo):
    items = []
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        term, traffic, news = "", 0, []
        for child in item:
            name = _local(child.tag)
            if name == "title":
                term = (child.text or "").strip()
            elif name == "approx_traffic":
                traffic = _traffic(child.text)
            elif name == "news_item":
                n = {_local(c.tag): (c.text or "").strip() for c in child}
                if n.get("news_item_url"):
                    news.append({"title": n.get("news_item_title", ""),
                                 "url": n["news_item_url"],
                                 "source": n.get("news_item_source", "")})
        if term:
            items.append({"term": term, "traffic": traffic, "news": news, "geo": geo})
    return items


def _fetch_geo(geo):
    for tmpl in URLS:
        try:
            r = requests.get(tmpl.format(geo=geo), headers=HEADERS, timeout=20)
            if r.status_code == 200 and "<item" in r.text:
                return _parse(r.text, geo)
        except Exception as e:
            print(f"  trends {geo} failed: {str(e)[:80]}")
    return []


def _load_cache():
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        if time.time() - data.get("at", 0) < CACHE_MAX_AGE:
            return data.get("items", [])
    except Exception:
        pass
    return []


def fetch_all(cfg):
    """Trending searches for every geo any channel asks for, de-duplicated by term,
    keeping the highest traffic and remembering which geos it trended in."""
    geos = []
    for ch in cfg["channels"].values():
        for g in ch.get("trends_geo", ["IN"]):
            if g not in geos:
                geos.append(g)
    merged = {}
    for g in geos:
        for it in _fetch_geo(g):
            key = it["term"].lower()
            cur = merged.get(key)
            if cur is None:
                merged[key] = {**it, "geos": [g]}
            else:
                cur["traffic"] = max(cur["traffic"], it["traffic"])
                cur["news"] = cur["news"] or it["news"]
                if g not in cur["geos"]:
                    cur["geos"].append(g)
    items = sorted(merged.values(), key=lambda x: -x["traffic"])
    if items:
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps({"at": time.time(), "items": items},
                                        ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        print(f"trends: {len(items)} trending searches ({', '.join(geos)})")
        return items
    cached = _load_cache()
    print(f"trends: live fetch empty, using {len(cached)} cached" if cached
          else "trends: unavailable, continuing without a trend boost")
    return cached


def matches(text, items):
    """Trending terms that appear in the text. A multi-word term matches when every
    word of 3+ letters is present, so 'iphone 17 price' still hits 'iPhone 17 launch'."""
    blob = text.lower()
    hits = []
    for it in items:
        term = it["term"].lower()
        words = [w for w in re.findall(r"\w+", term) if len(w) >= 3]
        if not words:
            continue
        if term in blob or (len(words) > 1 and all(w in blob for w in words)):
            hits.append(it)
    return hits


def boost(hits):
    """Score bonus: a base for being trending at all, plus log-scaled search volume."""
    if not hits:
        return 0
    best = max(h["traffic"] for h in hits)
    return 6 + min(6, int(math.log10(best + 1)))
