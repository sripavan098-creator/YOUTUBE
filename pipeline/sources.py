import re

import feedparser
import trafilatura

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


def top_stories(n=20):
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
            items.append({
                "url": url,
                "title": title,
                "summary": summary,
                "score": sum(v for k, v in W.items() if k in blob),
                "fits_india": any(k in blob for k in INDIA_KW),
                "fits_south": any(k in blob for k in SOUTH_KW),
            })
    items.sort(key=lambda x: -x["score"])
    out = []
    for it in items[:n]:
        out.append({**it, "body": _fetch_body(it["url"], it["summary"])})
    return out
