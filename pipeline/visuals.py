"""B-roll fetching. Unsplash is the primary source; Wikimedia Commons provides a
no-key fallback for public-domain/CC0 photos. Pexels videos are optional.

Unsplash demo apps are limited to 50 requests/hour, and a batch of 8 Shorts needs ~56
searches. So every search result list is cached on disk (a repeated query costs nothing),
and the remaining quota is read from Unsplash's own headers. When the demo quota is low,
the fetcher skips Unsplash and continues with available fallbacks rather than blocking
the batch. Set UNSPLASH_WAIT=1 to opt into waiting for the hourly reset. Apply for
Production access (free, 5,000/hour) in the Unsplash developer dashboard to lift the limit.
"""
import json
import os
import pathlib
import re
import time
import unicodedata

import requests

from pipeline import retention as R

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "out" / "unsplash_cache.json"
WIKIMEDIA_CACHE = ROOT / "out" / "wikimedia_cache.json"
UNSPLASH = "https://api.unsplash.com"
WIKIMEDIA = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_HEADERS = {
    "User-Agent": "YOUTUBE-shorts-pipeline/1.0 (https://github.com/sripavan098-creator/YOUTUBE)"
}
PEXELS = "https://api.pexels.com"
MAX_CLIP_SEC = 20
MIN_QUOTA = 2          # stop spending requests when this few remain
MAX_WAIT_SEC = 3700    # never sleep longer than one rate-limit window

_quota = {"remaining": None}


def _load_cache(path=CACHE):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache, path=CACHE):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _download(url, path, headers=None):
    r = requests.get(url, timeout=120, stream=True, headers=headers)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    return path


_VISUAL_STOP_WORDS = {
    "and", "for", "from", "with", "india", "indian", "photo", "image", "picture",
    "showing", "about", "the", "of", "a", "an",
}


def _visual_tokens(text):
    tokens = set()
    current = []
    for char in str(text).casefold():
        category = unicodedata.category(char)[0]
        if category in ("L", "N") or (category == "M" and current):
            current.append(char)
        elif current:
            token = "".join(current)
            if len(token) > 2 and token not in _VISUAL_STOP_WORDS:
                tokens.add(token)
            current = []
    if current:
        token = "".join(current)
        if len(token) > 2 and token not in _VISUAL_STOP_WORDS:
            tokens.add(token)
    return tokens


def _relevance_score(query, description):
    wanted = _visual_tokens(query)
    if not wanted:
        return 0
    return len(wanted & _visual_tokens(description))


def _is_relevant(query, description):
    """Only accept stock results whose indexed description supports the search query."""
    wanted = _visual_tokens(query)
    if not wanted:
        return False
    minimum = 2 if len(wanted) > 3 else 1
    return _relevance_score(query, description) >= minimum


# ---------------------------------------------------------------- Unsplash

def _unsplash_headers():
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    return {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"} if key else None


def _wait_for_quota():
    """Sleep to the top of the next hour, when the 50/hour window resets."""
    if os.environ.get("UNSPLASH_WAIT", "0") != "1":
        return False
    now = time.time()
    wait = min(MAX_WAIT_SEC, 3600 - (now % 3600) + 30)
    print(f"  Unsplash quota used up; waiting {int(wait // 60)} min for the next hour "
          f"(set UNSPLASH_WAIT=0 to skip waiting)", flush=True)
    time.sleep(wait)
    _quota["remaining"] = None
    return True


def _unsplash_search(q):
    """Up to 10 portrait photos for a query, from cache when possible."""
    h = _unsplash_headers()
    if not h:
        return []
    cache = _load_cache()
    if q in cache and all("description" in item for item in cache[q]):
        return cache[q]
    if _quota["remaining"] is not None and _quota["remaining"] < MIN_QUOTA:
        if not _wait_for_quota():
            return []
    r = requests.get(f"{UNSPLASH}/search/photos", headers=h, timeout=30,
                     params={"query": q, "orientation": "portrait", "per_page": 10,
                             "content_filter": "high"})
    rem = r.headers.get("X-Ratelimit-Remaining")
    if rem is not None:
        _quota["remaining"] = int(rem)
    if r.status_code == 403:  # rate limited
        _quota["remaining"] = 0
        if _wait_for_quota():
            return _unsplash_search(q)
        return []
    r.raise_for_status()
    results = [{
        "id": p["id"],
        "raw": p["urls"]["raw"],
        "regular": p["urls"]["regular"],
        "dl": p["links"].get("download_location"),
        "by": p["user"]["name"],
        "description": " ".join(
            [p.get("alt_description") or "", p.get("description") or ""] +
            [tag.get("title", "") for tag in p.get("tags", [])]
        ),
    } for p in r.json().get("results", [])]
    cache[q] = results
    _save_cache(cache)
    return results


def _unsplash_photo(q, used, dest):
    candidates = [
        p for p in _unsplash_search(q)
        if ("u", p["id"]) not in used
        and _is_relevant(q, p.get("description", ""))
    ]
    ranked = sorted(
        candidates,
        key=lambda p: R.rank_results([p], q)[1],
        reverse=True,
    )
    for p in ranked:
        blob = p.get("description", "").lower()
        if any(bad in blob for bad in R.BAD_VISUAL):
            continue
        used.add(("u", p["id"]))
        sep = "&" if "?" in p["raw"] else "?"
        url = f"{p['raw']}{sep}w=1080&h=1920&fit=crop&crop=entropy&q=80&fm=jpg"
        path = _download(url, dest.with_suffix(".jpg"))
        if not R.vision_ok(str(path), q):
            continue
        if p.get("dl"):
            try:
                requests.get(p["dl"], headers=_unsplash_headers(), timeout=10)
            except Exception:
                pass
        return path
    return None


# ---------------------------------------------------------------- Wikimedia Commons (no API key)

def _wikimedia_search(q):
    """Find cached public-domain/CC0 image results from Wikimedia Commons."""
    cache = _load_cache(WIKIMEDIA_CACHE)
    if cache.get(q):
        return cache[q]
    r = requests.get(
        WIKIMEDIA, headers=WIKIMEDIA_HEADERS, timeout=30,
        params={
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "generator": "search",
            "gsrnamespace": 6,
            "gsrsearch": f"filetype:bitmap {q}",
            "gsrlimit": 10,
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
            "iiurlwidth": 1080,
        },
    )
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", [])
    results = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        metadata = info.get("extmetadata", {})
        license_name = metadata.get("LicenseShortName", {}).get("value", "")
        normalized_license = license_name.casefold()
        if "cc0" not in normalized_license and "public domain" not in normalized_license:
            continue
        mime = info.get("mime", "")
        extension = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }.get(mime)
        image_url = info.get("thumburl") or info.get("url")
        if not extension or not image_url:
            continue
        results.append({
            "id": page.get("pageid"),
            "url": image_url,
            "extension": extension,
            "title": page.get("title", ""),
            "description": metadata.get("ImageDescription", {}).get("value", ""),
            "source": info.get("descriptionurl", ""),
            "license": license_name,
        })
    if results:
        cache[q] = results
        _save_cache(cache, WIKIMEDIA_CACHE)
    return results


def _wikimedia_photo(q, used, dest):
    candidates = [
        photo for photo in _wikimedia_search(q)
        if _is_relevant(q, f"{photo.get('title', '')} {photo.get('description', '')}")
    ]
    candidates.sort(
        key=lambda photo: _relevance_score(
            q, f"{photo.get('title', '')} {photo.get('description', '')}"
        ),
        reverse=True,
    )
    for photo in candidates:
        image_id = ("w", photo["id"])
        if image_id in used:
            continue
        path = _download(photo["url"], dest.with_suffix(photo["extension"]),
                         headers=WIKIMEDIA_HEADERS)
        used.add(image_id)
        return path
    return None


# ---------------------------------------------------------------- Pexels (optional)

def _pexels_headers():
    key = os.environ.get("PEXELS_API_KEY")
    return {"Authorization": key} if key else None


def _pexels_video(q, used, dest):
    h = _pexels_headers()
    if not h:
        return None
    r = requests.get(f"{PEXELS}/videos/search", headers=h, timeout=30,
                     params={"query": q, "orientation": "portrait", "size": "medium",
                             "per_page": 8})
    r.raise_for_status()
    for v in r.json().get("videos", []):
        if ("pv", v["id"]) in used or v.get("duration", 0) > MAX_CLIP_SEC:
            continue
        if not _is_relevant(q, v.get("url", "")):
            continue
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and (f.get("height") or 0) >= 1280]
        if not files:
            continue
        best = min(files, key=lambda f: f["height"])
        used.add(("pv", v["id"]))
        return _download(best["link"], dest.with_suffix(".mp4"))
    return None


# ---------------------------------------------------------------- public

def fetch_shots(keywords, dest_dir):
    """Return one unique local media path per keyword, or None for a designed scene.

    Stock media must have indexed subject overlap. If no relevant photo or clip exists,
    the renderer creates a keyword-labeled illustrated scene instead of a blank frame or
    unrelated stock.
    """
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    used, paths = set(), []

    for i, q in enumerate(keywords):
        dest = dest_dir / str(i)
        # Preserve the subject in every retry. A generic stock image is worse than
        # a designed poster that visibly carries the spoken line.
        ladder = [q]
        if q.strip() and "india" not in q.casefold():
            ladder.append(f"{q} India")

        got = None
        for query in ladder:
            for fn in (_unsplash_photo, _wikimedia_photo, _pexels_video):
                try:
                    got = fn(query, used, dest)
                except Exception as e:
                    print(f"  {fn.__name__} failed for '{query}': {str(e)[:100]}")
                if got:
                    break
            if got:
                break

        # None keeps alignment with beats — renderer draws a designed poster,
        # which looks intentional. A repeated photo looks lazy, so we never fall
        # back to the previous beat's path.
        paths.append(str(got) if got else None)
        if not got:
            print(f"  no footage for '{q}' -> poster scene")
    return paths
