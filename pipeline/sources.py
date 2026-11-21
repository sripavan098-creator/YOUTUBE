import re

import feedparser
import trafilatura

from pipeline import trends as gtrends

FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://venturebeat.com/category/ai/feed/",
    "https://blog.google/technology/ai/rss/",
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/rss.xml",
    "https://hnrss.org/newest?q=AI+OR+Google+OR+Amazon&points=50",
]

W = {"ai": 3, "openai": 4, "google": 4, "gemini": 4, "amazon": 4, "aws": 3, "nvidia": 3,
     "gpu": 2, "iphone": 3, "android": 2, "launch": 2, "released": 2, "chip": 2,
     "robot": 2, "india": 3}

INDIA_KW = {"india", "jio", "reliance", "tata", "flipkart", "swiggy", "zomato", "paytm",
            "phonepe", "upi", "rupee", "inr", "delhi", "mumbai", "bangalore", "hyderabad",
            "chennai", "bsnl", "airtel", "oneplus", "xiaomi", "redmi", "realme", "vivo",
            "oppo", "samsung india"}

SOUTH_KW = {"hyderabad", "bangalore", "chennai", "tamil", "telugu", "kannada", "malayalam",
            "kerala", "karnataka", "tamil nadu", "andhra", "telangana", "tcs", "infosys",
            "wipro", "isro", "iitm", "iisc", "iiit"}


def _fetch_body(url, fallback):
    try:
        html = trafilatura.fetch_url(url)
        if not html:
            return fallback
        return (trafilatura.extract(html) or fallback)[:3500]
    except Exception:
        return fallback


def top_stories(n=20, trend_items=None):
    trend_items = trend_items or []
    items, seen_urls = [], set()
    for feed in FEEDS:
        try:
            entries = feedparser.parse(feed).entries[:15]
        except Exception as e:
            print(f"feed skip {feed}: {e}")
            continue
        for e in entries:
            url = e.get("link")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = e.get("title", "")
            summary = re.sub("<[^>]+>", "", e.get("summary", ""))[:500]
            blob = (title + " " + summary).lower()
            hits = gtrends.matches(blob, trend_items)
            south_trend = any(g in ("IN-AP", "IN-TG") for h in hits for g in h["geos"])
            items.append({
                "url": url,
                "title": title,
                "summary": summary,
                "score": sum(v for k, v in W.items() if k in blob) + gtrends.boost(hits),
                "fits_india": any(k in blob for k in INDIA_KW),
                "fits_south": any(k in blob for k in SOUTH_KW) or south_trend,
                "trend_hits": [h["term"] for h in hits],
            })
    # Stories born from Google Trends itself: a trending search whose news is tech-related
    # is a topic people are asking about right now, even if no RSS feed above covered it.
    for it in trend_items[:25]:
        blob = (it["term"] + " " + " ".join(n["title"] for n in it["news"])).lower()
        tech = sum(v for k, v in W.items() if k in blob)
        if tech < 3 or not it["news"]:
            continue
        n0 = it["news"][0]
        if n0["url"] in seen_urls:
            continue
        seen_urls.add(n0["url"])
        items.append({
            "url": n0["url"], "title": n0["title"] or it["term"], "summary": n0["title"],
            "score": tech + gtrends.boost([it]) + 2,
            "fits_india": True,
            "fits_south": any(g in ("IN-AP", "IN-TG") for g in it["geos"]),
            "trend_hits": [it["term"]],
        })
    items.sort(key=lambda x: -x["score"])
    out = []
    for it in items[:n]:
        out.append({**it, "body": _fetch_body(it["url"], it["summary"])})
    return out
