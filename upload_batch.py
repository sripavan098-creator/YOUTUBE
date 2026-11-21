import os, sys, pathlib, json, time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = pathlib.Path(__file__).parent
OUT_DIR = ROOT / "out"
TOKENS_DIR = ROOT / "tokens"

def load_creds(channel):
    token_path = TOKENS_DIR / f"yt_{channel}.json"
    if not token_path.exists():
        print(f"❌ Missing {token_path}. Run auth script for {channel}")
        return None
    
    with open(token_path) as f:
        data = json.load(f)
        
    # FIX: Handle both 'token' and 'access_token' keys
    access_token = data.get('token') or data.get('access_token')
    
    if not access_token:
        print(f"❌ No access token found in {token_path}")
        return None

    return Credentials(
        token=access_token,
        refresh_token=data.get('refresh_token'),
        token_uri=data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        scopes=['https://www.googleapis.com/auth/youtube.upload']
    )

def upload_video(youtube, filepath, title, description, tags, privacy="private"):
    body = {
        'snippet': {'title': title[:100], 'description': description[:5000], 'tags': tags, 'categoryId': '28'},
        'status': {'privacyStatus': privacy}
    }
    media = MediaFileUpload(str(filepath), chunksize=-1, resumable=True)
    req = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    resp = req.execute()
    return resp['id']

def meta_for(mp4):
    """Read the metadata the pipeline wrote next to the render.

    Returns None when there is no sidecar. Callers must skip rather than fall
    back to the filename: that fallback is what published "25", "18", "17".
    """
    side = mp4.with_name(mp4.name.replace(".mp4", ".meta.json"))
    if not side.exists():
        return None
    data = json.loads(side.read_text(encoding="utf-8"))
    title = (data.get("title") or "").strip()
    if not title:
        return None
    return {
        "title": title[:100],
        "description": (data.get("description") or "")[:5000],
        "tags": [h.lstrip("#") for h in data.get("hashtags", [])][:15],
    }


channels = {"hi": "@vincodez", "te": "@techmuchatlu-official"}
for lang, handle in channels.items():
    creds = load_creds(lang)
    if not creds: continue
    
    yt = build('youtube', 'v3', credentials=creds)
    files = sorted(OUT_DIR.glob(f"*_{lang}.mp4"))
    
    if not files:
        print(f"No _{lang}.mp4 files found.")
        continue
        
    print(f"\n🚀 Uploading {len(files)} {lang.upper()} videos...")
    for i, fp in enumerate(files, 1):
        try:
            marker = fp.with_name(fp.name.replace(".mp4", ".uploaded.json"))
            if marker.exists():
                print(f"   [skip] {fp.name}: already uploaded "
                      f"({json.loads(marker.read_text()).get('id')})")
                continue
            meta = meta_for(fp)
            if not meta:
                print(f"   [skip] {fp.name}: no .meta.json beside it "
                      f"(refusing to publish a filename-derived title)")
                continue
            vid_id = upload_video(yt, fp, meta["title"], meta["description"], meta["tags"])
            marker.write_text(json.dumps({"id": vid_id}), encoding="utf-8")
            print(f"   ✅ [{i}/{len(files)}] {fp.name} -> ID: {vid_id}")
            time.sleep(2) 
        except Exception as e:
            print(f"   ❌ [{i}/{len(files)}] {fp.name} FAILED: {e}")

print("\n🎉 Batch upload complete! Check YouTube Studio.")
