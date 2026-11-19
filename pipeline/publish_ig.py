import json
import pathlib
import time

import requests

from pipeline import host

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://graph.instagram.com/v23.0"
POLL_INTERVAL = 10
POLL_TRIES = 60


def _token(lang):
    return json.loads((ROOT / "tokens" / f"ig_{lang}.json").read_text(encoding="utf-8"))


def publish(lang, path, caption, name):
    tok = _token(lang)
    ig_id, access = tok["user_id"], tok["access_token"]
    public_url = host.upload(path, name)
    try:
        container = requests.post(f"{BASE}/{ig_id}/media", data={
            "media_type": "REELS",
            "video_url": public_url,
            "caption": caption[:2200],
            "share_to_feed": "true",
            "access_token": access,
        }, timeout=120).json()
        if "id" not in container:
            raise RuntimeError(f"container create failed: {container}")

        for _ in range(POLL_TRIES):
            st = requests.get(f"{BASE}/{container['id']}", params={
                "fields": "status_code,status", "access_token": access}, timeout=60).json()
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"container {code}: {st.get('status')}")
            time.sleep(POLL_INTERVAL)
        else:
            raise RuntimeError("container never reached FINISHED")

        result = requests.post(f"{BASE}/{ig_id}/media_publish", data={
            "creation_id": container["id"], "access_token": access}, timeout=120).json()
        if "id" not in result:
            raise RuntimeError(f"publish failed: {result}")
        return result["id"]
    finally:
        try:
            host.delete(name)
        except Exception as e:
            print(f"host cleanup failed for {name}: {e}")
