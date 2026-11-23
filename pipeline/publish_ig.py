import os
import pathlib
import sys
import threading

import requests
from dotenv import load_dotenv
from instagrapi import Client

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
MAKE_WEBHOOK_URL = os.getenv("MAKE_IG_WEBHOOK_URL", "")

DEVICE = {
    "manufacturer": "Xiaomi",
    "model": "M2007J20CG",
    "android_version": 30,
    "android_release": "11",
}

_clients = {}
_lock = threading.Lock()


def _session_path(user):
    return ROOT / f"session_{user}.json"


def _get_client(lang):
    """Log in once per account and reuse its cached session."""
    user = os.getenv(f"IG_USER_{lang.upper()}")
    pwd = os.getenv(f"IG_PASS_{lang.upper()}")
    if not user or not pwd:
        raise RuntimeError(
            f"Missing IG_USER_{lang.upper()}/IG_PASS_{lang.upper()} in .env"
        )

    with _lock:
        if user in _clients:
            return _clients[user]

        cl = Client()
        cl.set_device(DEVICE)
        sess = _session_path(user)

        if sess.exists():
            try:
                cl.load_settings(str(sess))
                cl.get_followers()
                print(f"♻️  Reused cached session for @{user}")
                _clients[user] = cl
                return cl
            except Exception:
                print(f"⚠️  Stale session for @{user}, re-logging in...")
                sess.unlink(missing_ok=True)

        print(f"🔑 Logging in @{user} (first time only)...")
        try:
            cl.login(user, pwd)
        except Exception as e:
            msg = str(e)
            if "checkpoint" in msg.lower() or "challenge" in msg.lower():
                print("🚨 Instagram wants a verification code. Check SMS/email, then run again.")
            raise
        cl.dump_settings(str(sess))
        if sess.exists():
            sess.chmod(0o600)
        print(f"✅ Logged in + session cached for @{user}")
        _clients[user] = cl
        return cl


def publish(lang, path, caption, name=None):
    """Upload a Reel for the scheduled pipeline and return its media ID."""
    video_path = pathlib.Path(path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    client = _get_client(lang)
    media = client.clip_upload(path=video_path, caption=caption)
    print(f"✅ Reel posted to @{os.getenv(f'IG_USER_{lang.upper()}')}")
    return str(media.pk)


def upload_reel(video_path, caption, lang):
    video_path = str(video_path)
    if not pathlib.Path(video_path).is_file():
        print(f"❌ Video not found: {video_path}")
        return False

    if not MAKE_WEBHOOK_URL:
        print("❌ MAKE_IG_WEBHOOK_URL not set in .env")
        return False

    try:
        print(f"🚀 Uploading {lang} reel to temp host for Make.com...")
        with open(video_path, "rb") as video_file:
            response = requests.post(
                "https://tmpfiles.org/api/v2/upload",
                files={
                    "file": (
                        pathlib.Path(video_path).name,
                        video_file,
                        "video/mp4",
                    )
                },
                timeout=60,
            )
        response.raise_for_status()

        upload_data = response.json()
        if not isinstance(upload_data, dict) or not isinstance(
            upload_data.get("data"), dict
        ):
            raise ValueError("Temporary host returned an invalid upload response")
        temp_url = upload_data["data"].get("url")
        if not isinstance(temp_url, str):
            raise ValueError("Temporary host response did not include a URL")
        temp_url = temp_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        print(f"✅ Temp URL generated: {temp_url}")

        print("📡 Sending payload to Make.com...")
        webhook_response = requests.post(
            MAKE_WEBHOOK_URL,
            json={"video_url": temp_url, "caption": caption, "lang": lang},
            timeout=30,
        )
        if webhook_response.status_code != 200:
            print(
                f"❌ Make.com failed: {webhook_response.status_code} - "
                f"{webhook_response.text}"
            )
            return False

        print("✅ SUCCESS! Reel queued for posting via Make.com")
        return True
    except (OSError, requests.RequestException, ValueError) as e:
        print(f"❌ Upload error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python publish_ig.py <video_path> <lang> [caption]")

    video = sys.argv[1]
    lang = sys.argv[2]
    caption = sys.argv[3] if len(sys.argv) > 3 else (
        "AI pipeline test 🚀 #techmuchatlu #telugutech"
    )
    sys.exit(0 if upload_reel(video, caption, lang) else 1)
