import os
import requests
import pathlib

def fetch_shots(keywords, dest_dir):
    """
    Bulletproof Unsplash image fetcher. 
    Completely replaces Pexels to avoid 401 Unauthorized errors.
    """
    dest = pathlib.Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    
    api_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    if not api_key:
        print("⚠️ UNSPLASH_ACCESS_KEY missing in .env. Skipping image fetch.", flush=True)
        return []

    headers = {"Authorization": f"Client-ID {api_key}"}
    
    # Fetch up to 6 shots per video
    for i, q in enumerate(keywords[:6]):
        try:
            # 1. Try the specific keyword
            r = requests.get(
                "https://api.unsplash.com/search/photos", 
                headers=headers,
                params={"query": q, "orientation": "portrait", "per_page": 1}, 
                timeout=10
            )
            r.raise_for_status()
            data = r.json()
            
            # 2. Fallback to 'technology' if the specific keyword yields nothing
            if not data.get("results"):
                r = requests.get(
                    "https://api.unsplash.com/search/photos", 
                    headers=headers,
                    params={"query": "technology", "orientation": "portrait", "per_page": 1}, 
                    timeout=10
                )
                r.raise_for_status()
                data = r.json()
                
            # 3. Download and save
            if data.get("results"):
                img_url = data["results"][0]["urls"]["regular"]
                p = dest / f"{i}.jpg"
                
                img_data = requests.get(img_url, timeout=15).content
                p.write_bytes(img_data)
                paths.append(str(p))
            else:
                paths.append("")
                
        except Exception as e:
            print(f"  ⚠️ Unsplash fetch failed for '{q}': {e}", flush=True)
            paths.append("")
            
    return paths
