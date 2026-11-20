import os
import requests

def fetch_shots(keywords, dest_dir):
    """Fetches portrait images from Unsplash API."""
    os.makedirs(dest_dir, exist_ok=True)
    paths = []
    headers = {"Authorization": f"Client-ID {os.environ['UNSPLASH_ACCESS_KEY']}"}

    for i, q in enumerate(keywords[:4]):
        try:
            # Search Unsplash for portrait orientation
            r = requests.get(
                "https://api.unsplash.com/search/photos",
                headers=headers,
                params={"query": q, "orientation": "portrait", "per_page": 1},
                timeout=30
            )
            r.raise_for_status()
            data = r.json()

            # Fallback to 'technology' if the specific keyword fails
            if not data.get("results"):
                r = requests.get(
                    "https://api.unsplash.com/search/photos",
                    headers=headers,
                    params={"query": "technology", "orientation": "portrait", "per_page": 1},
                    timeout=30
                )
                r.raise_for_status()
                data = r.json()

            if data.get("results"):
                # Unsplash uses 'urls']['regular'] for a good quality image
                img_url = data["results"][0]["urls"]["regular"]
                p = os.path.join(dest_dir, f"{i}.jpg")

                # Download the image
                img_data = requests.get(img_url, timeout=60).content
                with open(p, "wb") as handler:
                    handler.write(img_data)
                paths.append(p)
        except Exception as e:
            print(f"Failed to fetch image for '{q}': {e}")

    return paths
