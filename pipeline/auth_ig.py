import json
import os
import pathlib
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: python -m pipeline.auth_ig <hi|te|en> <CODE>")
    lang, code = sys.argv[1], sys.argv[2]

    short = requests.post("https://api.instagram.com/oauth/access_token", data={
        "client_id": os.environ["IG_APP_ID"],
        "client_secret": os.environ["IG_APP_SECRET"],
        "grant_type": "authorization_code",
        "redirect_uri": os.environ["IG_REDIRECT"],
        "code": code,
    }, timeout=60).json()
    if "access_token" not in short:
        sys.exit(f"code exchange failed: {short}")

    long_lived = requests.get("https://graph.instagram.com/access_token", params={
        "grant_type": "ig_exchange_token",
        "client_secret": os.environ["IG_APP_SECRET"],
        "access_token": short["access_token"],
    }, timeout=60).json()
    if "access_token" not in long_lived:
        sys.exit(f"long-lived exchange failed: {long_lived}")

    (ROOT / "tokens").mkdir(exist_ok=True)
    (ROOT / "tokens" / f"ig_{lang}.json").write_text(json.dumps({
        "user_id": short["user_id"],
        "access_token": long_lived["access_token"],
    }), encoding="utf-8")
    print(f"saved tokens/ig_{lang}.json (60-day token)")


if __name__ == "__main__":
    main()
