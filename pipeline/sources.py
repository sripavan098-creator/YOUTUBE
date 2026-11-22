import re

import feedparser
import trafilatura

from pipeline import trends as gtrends

# ── Tech-only RSS feeds ──────────────────────────────────────────────────────
# Every feed here is EXCLUSIVELY tech / startup / AI.
# Non-tech sections of Verge/TechCrunch are excluded by using category URLs.
FEEDS = [
    # Global AI & tech news
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://techcrunch.com/category/apps/feed/",
    "https://techcrunch.com/category/gadgets/feed/",
    "https://techcrunch.com/category/startups/feed/",
    "https://www.theverge.com/tech/rss/index.xml",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "https://venturebeat.com/category/ai/feed/",
    "https://venturebeat.com/category/mobile/feed/",
    # Official AI lab blogs
    "https://blog.google/technology/ai/rss/",
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/rss.xml",
    # India-specific tech
    "https://gadgets.ndtv.com/rss/feeds",
    "https://www.gadgets360.com/rss/news",
    "https://inc42.com/feed/",
    "https://yourstory.com/feed",
    # Hacker News — tech/startup filter, min 50 points
    "https://hnrss.org/newest?q=AI+OR+Google+OR+Amazon+OR+startup+OR+chip&points=50",
    "https://hnrss.org/newest?q=India+tech+OR+fintech+OR+SaaS&points=30",
]

# ── Scoring weights ──────────────────────────────────────────────────────────
W = {
    # AI / ML
    "ai": 3, "artificial intelligence": 3, "machine learning": 3, "deep learning": 3,
    "llm": 4, "openai": 4, "chatgpt": 4, "gemini": 4, "claude": 4, "gpt": 4,
    "mistral": 3, "meta ai": 3, "anthropic": 4,
    # Big tech
    "google": 3, "amazon": 3, "aws": 3, "microsoft": 3, "apple": 3, "nvidia": 4,
    "tesla": 2, "spacex": 2,
    # Hardware / chips
    "gpu": 3, "chip": 3, "processor": 2, "semiconductor": 3, "snapdragon": 3,
    # Devices
    "iphone": 3, "android": 3, "smartphone": 2, "laptop": 2, "headset": 2,
    # Software / apps
    "app": 2, "software": 2, "platform": 2, "launch": 2, "released": 2,
    "update": 2, "feature": 2, "version": 2,
    # Startup / funding
    "startup": 3, "funding": 3, "series a": 3, "series b": 3, "unicorn": 3,
    "ipo": 3, "valuation": 2, "investment": 2, "raise": 2,
    # India tech
    "india": 2, "jio": 3, "reliance": 2, "tata": 2, "infosys": 3, "wipro": 3,
    "tcs": 3, "isro": 4, "upi": 3, "fintech": 3, "edtech": 3,
    # Robotics / future
    "robot": 3, "drone": 2, "autonomous": 2, "electric vehicle": 2, "ev": 2,
    # Cyber / security
    "cybersecurity": 3, "hack": 2, "breach": 2, "vulnerability": 2,
}

# ── HARD BLOCK — any story matching these is REJECTED immediately ─────────────
# These cover politics, sports, entertainment, weather, crime, health, etc.
BLOCK_KW = {
    # Sports
    "cricket", "ipl", "bcci", "sachin", "kohli", "dhoni", "virat",
    "football", "fifa", "nfl", "nba", "nhl", "mlb",
    "tennis", "wimbledon", "olympics", "medals", "athlete", "stadium",
    "match", "tournament", "championship", "league standings",
    # Politics / government (non-tech)
    "election", "parliament", "congress", "bjp", "aap", "aam aadmi",
    "modi", "rahul gandhi", "kejriwal", "yogi", "cm ", "chief minister",
    "prime minister", "president trump", "white house", "senate", "democrat",
    "republican", "vote", "ballot", "referendum", "protest", "demonstration",
    # Entertainment / Bollywood
    "bollywood", "tollywood", "kollywood", "box office", "film release",
    "actor", "actress", "celebrity", "movie review", "web series",
    "netflix drama", "ott release", "bigg boss", "reality show",
    "music album", "song release", "rap battle",
    # News / crime / disasters
    "murder", "rape", "accident", "flood", "earthquake", "cyclone",
    "explosion", "blast", "terror", "shooting", "riot", "violence",
    "crime", "police arrested", "court verdict", "jail sentence",
    # Health (non-tech medical — keep "health tech" / "medtech" allowed)
    "covid surge", "dengue", "malaria", "cancer treatment", "hospital",
    "vaccine mandate", "drug approval", "clinical trial", "diet", "nutrition",
    # Business/finance (non-tech)
    "stock market crash", "gold price", "crude oil", "inflation rate",
    "rbi repo rate", "income tax", "gst rate", "real estate prices",
    "property market", "mutual fund nav", "sensex crash", "nifty fall",
    # Weather / environment (non-tech)
    "monsoon", "rainfall", "heatwave", "smog", "air quality index", "aqi",
    # Lifestyle / travel / food
    "recipe", "restaurant review", "travel guide", "hotel booking",
    "fashion week", "beauty tips", "wedding", "honeymoon",
}

# Minimum combined tech score a story must reach to pass the is_tech gate
TECH_MIN_SCORE = 4

INDIA_KW = {"india", "jio", "reliance", "tata", "flipkart", "swiggy", "zomato", "paytm",
            "phonepe", "upi", "rupee", "inr", "delhi", "mumbai", "bangalore", "hyderabad",
            "chennai", "bsnl", "airtel", "oneplus", "xiaomi", "redmi", "realme", "vivo",
            "oppo", "samsung india"}

SOUTH_KW = {"hyderabad", "bangalore", "chennai", "tamil", "telugu", "kannada", "malayalam",
            "kerala", "karnataka", "tamil nadu", "andhra", "telangana", "tcs", "infosys",
            "wipro", "isro", "iitm", "iisc", "iiit"}


def is_tech(title: str, summary: str) -> tuple[bool, int]:
    """Return (passes, score).  A story passes only if:
       1. Its combined tech keyword score >= TECH_MIN_SCORE, AND
       2. None of its words match the BLOCK_KW hard-reject list.
    """
    blob = (title + " " + summary).lower()

    # Hard block first — fastest exit
    for kw in BLOCK_KW:
        if kw in blob:
            return False, 0

    score = sum(v for k, v in W.items() if k in blob)
    return score >= TECH_MIN_SCORE, score


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
    rejected = 0

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

            # ── TECH GATE: reject non-tech stories immediately ───────────────
            ok, tech_score = is_tech(title, summary)
            if not ok:
                rejected += 1
                continue

            blob = (title + " " + summary).lower()
            hits = gtrends.matches(blob, trend_items)
            south_trend = any(g in ("IN-AP", "IN-TG") for h in hits for g in h["geos"])
            items.append({
                "url": url,
                "title": title,
                "summary": summary,
                "score": tech_score + gtrends.boost(hits),
                "fits_india": any(k in blob for k in INDIA_KW),
                "fits_south": any(k in blob for k in SOUTH_KW) or south_trend,
                "trend_hits": [h["term"] for h in hits],
            })

    if rejected:
        print(f"[sources] blocked {rejected} non-tech stories")

    # Stories born from Google Trends itself: a trending search whose news is tech-related
    # is a topic people are asking about right now, even if no RSS feed above covered it.
    for it in trend_items[:25]:
        trend_title = it["term"]
        trend_news = " ".join(n["title"] for n in it["news"])
        ok, tech_score = is_tech(trend_title, trend_news)
        if not ok or not it["news"]:
            continue
        n0 = it["news"][0]
        if n0["url"] in seen_urls:
            continue
        seen_urls.add(n0["url"])
        items.append({
            "url": n0["url"], "title": n0["title"] or it["term"], "summary": n0["title"],
            "score": tech_score + gtrends.boost([it]) + 2,
            "fits_india": True,
            "fits_south": any(g in ("IN-AP", "IN-TG") for g in it["geos"]),
            "trend_hits": [it["term"]],
        })

    items.sort(key=lambda x: -x["score"])
    out = []
    for it in items[:n]:
        out.append({**it, "body": _fetch_body(it["url"], it["summary"])})
    return out
