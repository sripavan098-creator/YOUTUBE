import os
import pathlib
import sys

from dotenv import load_dotenv
from instagrapi import Client

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def publish(lang, path, caption, name=None):
    """Upload a Reel directly with the account credentials for ``lang``."""
    video_path = pathlib.Path(path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    user_key = f"IG_USER_{lang.upper()}"
    password_key = f"IG_PASS_{lang.upper()}"
    user = os.getenv(user_key)
    password = os.getenv(password_key)
    if not user or not password:
        raise ValueError(f"Missing {user_key} or {password_key} in .env")

    print(f"Logging into Instagram as @{user}...")
    client = Client()
    if not client.login(user, password):
        raise RuntimeError(f"Instagram login failed for @{user}")

    print(f"Uploading Reel: {video_path.name}")
    media = client.clip_upload(path=video_path, caption=caption)
    print(f"Reel posted to @{user}")
    return str(media.pk)


def upload_reel(video_path, caption, lang):
    """Upload a Reel from the command line and report success as a boolean."""
    try:
        publish(lang, video_path, caption)
    except Exception as exc:
        print(f"Instagram upload failed: {exc}")
        return False
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python publish_ig.py <video_path> <lang> [caption]")
        sys.exit(1)

    video = sys.argv[1]
    lang = sys.argv[2]
    caption = sys.argv[3] if len(sys.argv) > 3 else (
        "Automated upload test! #techmuchatlu #ai #technews"
    )
    sys.exit(0 if upload_reel(video, caption, lang) else 1)
