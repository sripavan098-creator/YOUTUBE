"""B-roll fetching. Unsplash is the primary (and only required) source: portrait photos,
one per spoken line. Pexels is used only if PEXELS_API_KEY happens to be set.

Unsplash demo apps are limited to 50 requests/hour, and a batch of 8 Shorts needs ~56
searches. So every search result list is cached on disk (a repeated query costs nothing),
the remaining quota is read from Unsplash's own headers, and when it runs out the
fetcher waits for the next hour instead of failing. Apply for Production access (free,
5,000/hour) in the Unsplash developer dashboard to remove the wait.
"""
import json
import os
import pathlib
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "out" / "unsplash_cache.json"
UNSPLASH = "https://api.unsplash.com"
PEXELS = "https://api.pexels.com"
MAX_CLIP_SEC = 20
MIN_QUOTA = 2          # stop spending requests when this few remain
MAX_WAIT_SEC = 3700    # never sleep longer than one rate-limit window

_quota = {"remaining": None}


def _load_cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache):
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _download(url, path, headers=None):
    r = requests.get(url, timeout=120, stream=True, headers=headers)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    return path


# ---------------------------------------------------------------- Unsplash

def _unsplash_headers():
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    return {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"} if key else None


def _wait_for_quota():
    """Sleep to the top of the next hour, when the 50/hour window resets."""
    if os.environ.get("UNSPLASH_WAIT", "1") == "0":
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
    if q in cache:
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
    results = [{"id": p["id"], "raw": p["urls"]["raw"], "regular": p["urls"]["regular"],
                "dl": p["links"].get("download_location"),
                "by": p["user"]["name"]} for p in r.json().get("results", [])]
    cache[q] = results
    _save_cache(cache)
    return results


def _unsplash_photo(q, used, dest):
    for p in _unsplash_search(q):
        if ("u", p["id"]) in used:
            continue
        used.add(("u", p["id"]))
        # imgix params: exact 9:16 crop at 1080x1920, so Remotion gets a sharp, ready frame
        sep = "&" if "?" in p["raw"] else "?"
        url = f"{p['raw']}{sep}w=1080&h=1920&fit=crop&crop=entropy&q=80&fm=jpg"
        path = _download(url, dest.with_suffix(".jpg"))
        if p.get("dl"):  # Unsplash API guideline: report the download (not rate limited)
            try:
                requests.get(p["dl"], headers=_unsplash_headers(), timeout=10)
            except Exception:
                pass
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
    """Return one local media path per keyword, in order. If a query finds nothing it is
    retried with its last word, then a generic India-tech query, then the previous beat's
    photo, so a cut always lands on the beat."""
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    used, paths = set(), []
    for i, q in enumerate(keywords):
        dest = dest_dir / str(i)
        ladder = [q]
        if len(q.split()) > 1:
            ladder.append(q.split()[-1])
        ladder.append("india technology")
        got = None
        for query in ladder:
            for fn in (_unsplash_photo, _pexels_video):
                try:
                    got = fn(query, used, dest)
                except Exception as e:
                    print(f"  {fn.__name__} failed for '{query}': {str(e)[:100]}")
                if got:
                    break
            if got:
                break
        # None keeps the list aligned with the beats; the renderer draws a designed
        # poster for it, which looks intentional where a repeated photo looks lazy.
        paths.append(str(got) if got else None)
        if not got:
            print(f"  no footage for '{q}' -> poster scene")
    return paths
