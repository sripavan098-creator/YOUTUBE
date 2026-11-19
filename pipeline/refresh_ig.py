import json
import pathlib

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    files = sorted((ROOT / "tokens").glob("ig_*.json"))
    if not files:
        print("no IG tokens found")
        return
    for f in files:
        tok = json.loads(f.read_text(encoding="utf-8"))
        r = requests.get("https://graph.instagram.com/refresh_access_token", params={
            "grant_type": "ig_refresh_token",
            "access_token": tok["access_token"],
        }, timeout=60).json()
        if "access_token" in r:
            tok["access_token"] = r["access_token"]
            f.write_text(json.dumps(tok), encoding="utf-8")
            print(f"refreshed {f.name}")
        else:
            print(f"REFRESH FAILED {f.name}: {r}")


if __name__ == "__main__":
    main()
