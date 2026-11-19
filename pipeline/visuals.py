import os

import requests

FALLBACK_QUERY = "technology abstract"


def _search(query, headers):
    try:
        r = requests.get("https://api.pexels.com/v1/search", headers=headers,
                         params={"query": query, "orientation": "portrait", "per_page": 3},
                         timeout=30)
        r.raise_for_status()
        return r.json().get("photos") or []
    except Exception as e:
        print(f"pexels '{query}': {e}")
        return []


def _download(url, dest):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)


def fetch_shots(keywords, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
    paths = []
    for i, query in enumerate(keywords[:4]):
        photos = _search(query, headers) or _search(FALLBACK_QUERY, headers)
        if not photos:
            raise RuntimeError(f"pexels returned no photos for '{query}' and fallback")
        dest = os.path.join(dest_dir, f"{i}.jpg")
        _download(photos[0]["src"]["large2x"], dest)
        paths.append(dest)
    if not paths:
        raise RuntimeError("no b-roll downloaded")
    return paths
