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


def _extract_cover(video_path: pathlib.Path) -> pathlib.Path | None:
    """Extract the first frame of the video at 0.5s as a cover JPEG.

    Instagram Reels show a cover image chosen at upload time — without one
    IG picks a random frame that often looks blurry or mid-transition.
    We grab the same frame we use for YT thumbnails (hook card, 0.5 s).
    """
    import subprocess
    cover = video_path.with_suffix(".cover.jpg")
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(video_path),
             "-frames:v", "1", "-q:v", "2",
             "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                    "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
             str(cover)],
            check=True, timeout=30,
        )
        return cover if cover.is_file() else None
    except Exception as e:
        print(f"⚠️  Cover image extraction failed: {e}")
        return None


def publish(lang, path, caption, name=None, thumbnail=None):
    """Upload a Reel for the scheduled pipeline and return its media ID.

    thumbnail: optional path to a 1080×1920 JPEG cover image.
               When None, we extract one from the video at 0.5 s automatically
               so the Reel always has a clean hook-card cover.
    """
    video_path = pathlib.Path(path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    # Resolve cover image — extract from video if not provided
    cover_path = pathlib.Path(thumbnail) if thumbnail and pathlib.Path(thumbnail).is_file() \
        else _extract_cover(video_path)

    client = _get_client(lang)

    # instagrapi's clip_upload accepts an optional `thumbnail` kwarg since v2.x
    # Pass it when we have one; fall back gracefully for older versions.
    extra = {}
    if cover_path and cover_path.is_file():
        extra["thumbnail"] = cover_path

    attempts = 3
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            media = client.clip_upload(path=video_path, caption=caption, **extra)
            print(f"✅ Reel posted to @{os.getenv(f'IG_USER_{lang.upper()}')} "
                  f"(cover={'yes' if extra else 'no'})")
            return str(media.pk)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "login_required" in msg or "not_logged_in" in msg:
                print(f"⚠️  Session expired on attempt {attempt}, re-logging in...")
                # Clear cached client to force re-login
                user = os.getenv(f"IG_USER_{lang.upper()}")
                with _lock:
                    _clients.pop(user, None)
                sess = _session_path(user) if user else None
                if sess and sess.exists():
                    sess.unlink(missing_ok=True)
                try:
                    client = _get_client(lang)
                except Exception as login_err:
                    print(f"❌ Re-login failed: {login_err}")
                    raise
            elif attempt < attempts:
                import time
                print(f"⚠️  clip_upload attempt {attempt} failed: {e} — retrying in 5s...")
                time.sleep(5)
            else:
                raise RuntimeError(f"clip_upload failed after {attempts} attempts: {last_err}") \
                    from last_err
    raise RuntimeError(f"clip_upload failed: {last_err}") from last_err


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
