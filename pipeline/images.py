"""Real image fetcher for thumbnail backgrounds and B-roll overlays.

Replaces all placeholder/solid-colour backgrounds with real, relevant photos.

Sources (priority order, all free):
  1. Pixabay  — no attribution required, 100 req/min, free commercial use
                 Set PIXABAY_API_KEY (free at pixabay.com/api/docs/)
  2. Unsplash — attribution chip rendered on thumbnail
                 Set UNSPLASH_ACCESS_KEY (free at unsplash.com/developers)
  3. Pexels   — Set PEXELS_API_KEY if available
  4. Wikimedia Commons — no key needed, CC/public domain

Usage:
    from pipeline.images import fetch_background
    path = fetch_background("smartphone india", lang="hi", out_path="/tmp/bg.jpg")
    # returns a local JPEG path, or None if all sources fail (use gradient bg)
"""

import hashlib
import os
import pathlib
import random
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "images"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_TIMEOUT = 10

# ── Keyword expansion — search engines work best with English ─────────────────
_KW_MAP = {
    # Telugu
    "స్మార్ట్‌ఫోన్": "smartphone india",
    "ఆర్టిఫిషియల్ ఇంటెలిజెన్స్": "artificial intelligence technology",
    "యాప్": "mobile app smartphone",
    "ఇంటర్నెట్": "internet wifi india",
    "డేటా": "data privacy technology",
    "హైదరాబాద్": "hyderabad city india",
    "టెక్నాలజీ": "technology india",
    "గూగుల్": "google technology",
    "యూట్యూబ్": "youtube smartphone screen",
    "ఆన్‌లైన్": "online digital india",
    # Hindi
    "स्मार्टफोन": "smartphone india",
    "कृत्रिम बुद्धिमत्ता": "artificial intelligence technology",
    "ऐप": "mobile app smartphone",
    "इंटरनेट": "internet wifi india",
    "डेटा": "data privacy technology",
    "तकनीक": "technology india",
    "गूगल": "google technology",
    "यूट्यूब": "youtube smartphone",
    "ऑनलाइन": "online digital",
    "पैसा": "money rupees india",
    "नौकरी": "job work laptop india",
    "शिक्षा": "education student india",
}

_CATEGORY_DEFAULTS = {
    "ai_tools": "artificial intelligence robot technology",
    "earning_apps": "money smartphone app india",
    "free_alternatives": "laptop software technology",
    "phone_tips": "smartphone screen closeup",
    "ai_for_students": "student laptop studying",
    "govt_tech": "government digital india",
    "default": "technology india digital",
}


def _expand_query(query: str, lang: str = "en") -> str:
    """Replace native-script words with English equivalents for better image results."""
    result = query
    for native, english in _KW_MAP.items():
        result = result.replace(native, english)
    if any(ord(c) > 127 for c in result):
        suffix = "india technology" if lang in ("hi", "te") else "technology"
        result = f"{suffix} {result}"[:100]
    return result.strip()


def _cache_path(query: str, source: str) -> pathlib.Path:
    h = hashlib.md5(f"{source}:{query}".encode()).hexdigest()[:12]
    return CACHE_DIR / f"{h}.jpg"


def _download(url: str, dest: pathlib.Path) -> bool:
    """Download a URL to dest. Returns True on success."""
    try:
        r = requests.get(url, timeout=_TIMEOUT, stream=True,
                         headers={"User-Agent": "ShortsPipeline/1.0"})
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"  [images] download failed: {e}", flush=True)
        return False


# ── Source implementations ────────────────────────────────────────────────────

def _fetch_pixabay(query: str) -> str | None:
    """Pixabay: free commercial use, no attribution required. 100 req/min.

    Get a free key at: pixabay.com/api/docs/
    Set env var: PIXABAY_API_KEY=your-key
    """
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key:
        return None
    cached = _cache_path(query, "pixabay")
    if cached.exists():
        return str(cached)
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": key,
                "q": query,
                "image_type": "photo",
                "orientation": "horizontal",
                "min_width": 1280,
                "per_page": 8,
                "safesearch": "true",
                "order": "popular",
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        if not hits:
            return None
        hit = random.choice(hits[:5])
        url = hit.get("largeImageURL") or hit.get("webformatURL")
        if url and _download(url, cached):
            print(f"  [images] Pixabay: {query!r}", flush=True)
            return str(cached)
    except Exception as e:
        print(f"  [images] Pixabay error: {e}", flush=True)
    return None


def _fetch_unsplash(query: str) -> str | None:
    """Unsplash: 50 req/hour free. Attribution chip added to thumbnail.

    Get a free key at: unsplash.com/developers
    Set env var: UNSPLASH_ACCESS_KEY=your-key
    """
    key = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
    if not key:
        return None
    cached = _cache_path(query, "unsplash")
    if cached.exists():
        return str(cached)
    try:
        r = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 8, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {key}"},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        photo = random.choice(results[:5])
        url = photo["urls"].get("regular") or photo["urls"].get("full")
        if url and _download(url, cached):
            # Ping the download_location endpoint (required by Unsplash API terms)
            try:
                dl_loc = photo.get("links", {}).get("download_location")
                if dl_loc:
                    requests.get(dl_loc, headers={"Authorization": f"Client-ID {key}"}, timeout=5)
            except Exception:
                pass
            print(f"  [images] Unsplash: {query!r}", flush=True)
            return str(cached)
    except Exception as e:
        print(f"  [images] Unsplash error: {e}", flush=True)
    return None


def _fetch_pexels(query: str) -> str | None:
    """Pexels: 200/hour, 20k/month free. Attribution required.

    Set env var: PEXELS_API_KEY=your-key (new keys currently paused but old ones work)
    """
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    cached = _cache_path(query, "pexels")
    if cached.exists():
        return str(cached)
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 8, "orientation": "landscape"},
            headers={"Authorization": key},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if not photos:
            return None
        photo = random.choice(photos[:5])
        url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
        if url and _download(url, cached):
            print(f"  [images] Pexels: {query!r}", flush=True)
            return str(cached)
    except Exception as e:
        print(f"  [images] Pexels error: {e}", flush=True)
    return None


def _fetch_wikimedia(query: str) -> str | None:
    """Wikimedia Commons: no key, CC/public domain. No personal data in headers."""
    cached = _cache_path(query, "wikimedia")
    if cached.exists():
        return str(cached)
    try:
        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"file:{query} filetype:bitmap",
                "gsrnamespace": 6,
                "gsrlimit": 8,
                "prop": "imageinfo",
                "iiprop": "url|size",
                "iiurlwidth": 1280,
                "format": "json",
            },
            headers={"User-Agent": "ShortsPipeline/1.0"},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        candidates = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            w = info.get("thumbwidth", 0) or info.get("width", 0)
            if url and w >= 800:
                candidates.append(url)
        if not candidates:
            return None
        url = random.choice(candidates[:5])
        if _download(url, cached):
            print(f"  [images] Wikimedia: {query!r}", flush=True)
            return str(cached)
    except Exception as e:
        print(f"  [images] Wikimedia error: {e}", flush=True)
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_background(
    query: str,
    lang: str = "en",
    out_path: str | None = None,
    category: str = "default",
) -> str | None:
    """Fetch a real background image for the query.

    Args:
        query:    Search keywords (Telugu/Hindi OK — will be auto-expanded)
        lang:     "hi", "te", "en"
        out_path: If given, copy the image to this path and return it
        category: Fallback category if query returns no results

    Returns:
        Local file path (JPEG) or None if all sources fail.
    """
    en_query = _expand_query(query, lang)
    cat_q = _CATEGORY_DEFAULTS.get(category, _CATEGORY_DEFAULTS["default"])

    path = None
    for src in [_fetch_pixabay, _fetch_unsplash, _fetch_pexels, _fetch_wikimedia]:
        path = src(en_query)
        if path:
            break
        # Try category default if specific query failed
        if not path and cat_q != en_query:
            path = src(cat_q)
            if path:
                break
        time.sleep(0.2)

    if path and out_path:
        import shutil
        pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out_path)
        return out_path

    return path


def fetch_background_for_script(script: dict, lang: str = "en") -> str | None:
    """Convenience: extract the best search query from a script dict."""
    q = (
        script.get("image_query")
        or script.get("hook_text")
        or (script.get("beats") or [{}])[0].get("line", "")
        or script.get("title", "")
    )[:80]
    category = script.get("category", "default")
    return fetch_background(q, lang=lang, category=category)
