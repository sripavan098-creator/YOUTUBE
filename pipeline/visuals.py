"""B-roll fetching. Real portrait VIDEO from Pexels first (motion holds attention far
better than a zoomed still), then Pexels photos, then Unsplash photos if a key exists.

One query per beat, one result per query, never the same clip twice in a video.
"""
import os
import pathlib

import requests

PEXELS = "https://api.pexels.com"
MAX_CLIP_SEC = 20


def _pexels_headers():
    key = os.environ.get("PEXELS_API_KEY")
    return {"Authorization": key} if key else None


def _download(url, path):
    r = requests.get(url, timeout=120, stream=True)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    return path


def _pexels_video(q, used, dest):
    h = _pexels_headers()
    if not h:
        return None
    r = requests.get(f"{PEXELS}/videos/search", headers=h, timeout=30,
                     params={"query": q, "orientation": "portrait", "size": "medium",
                             "per_page": 8})
    r.raise_for_status()
    for v in r.json().get("videos", []):
        if v["id"] in used or v.get("duration", 0) > MAX_CLIP_SEC:
            continue
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and (f.get("height") or 0) >= 1280]
        if not files:
            continue
        best = min(files, key=lambda f: f["height"])  # smallest that is still sharp enough
        used.add(v["id"])
        return _download(best["link"], dest.with_suffix(".mp4"))
    return None


def _pexels_photo(q, used, dest):
    h = _pexels_headers()
    if not h:
        return None
    r = requests.get(f"{PEXELS}/v1/search", headers=h, timeout=30,
                     params={"query": q, "orientation": "portrait", "per_page": 6})
    r.raise_for_status()
    for p in r.json().get("photos", []):
        if ("p", p["id"]) in used:
            continue
        used.add(("p", p["id"]))
        return _download(p["src"]["portrait"], dest.with_suffix(".jpg"))
    return None


def _unsplash_photo(q, used, dest):
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        return None
    r = requests.get("https://api.unsplash.com/search/photos",
                     headers={"Authorization": f"Client-ID {key}"}, timeout=30,
                     params={"query": q, "orientation": "portrait", "per_page": 5})
    r.raise_for_status()
    for p in r.json().get("results", []):
        if ("u", p["id"]) in used:
            continue
        used.add(("u", p["id"]))
        return _download(p["urls"]["regular"], dest.with_suffix(".jpg"))
    return None


def fetch_shots(keywords, dest_dir):
    """Return one local media path per keyword, in order. A beat whose query finds
    nothing reuses the previous beat's media so cuts still land on the beat."""
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    used, paths = set(), []
    for i, q in enumerate(keywords):
        dest = dest_dir / str(i)
        got = None
        for fn in (_pexels_video, _pexels_photo, _unsplash_photo):
            try:
                got = fn(q, used, dest)
            except Exception as e:
                print(f"  {fn.__name__} failed for '{q}': {e}")
            if got:
                break
        if not got and q.split():
            # one broader retry on the last word of the query
            broad = q.split()[-1]
            for fn in (_pexels_video, _pexels_photo):
                try:
                    got = fn(broad, used, dest)
                except Exception:
                    got = None
                if got:
                    break
        if not got and paths:
            got = paths[-1]
        if got:
            paths.append(str(got))
        else:
            print(f"  no footage for '{q}'")
    return paths
