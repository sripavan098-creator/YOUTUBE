import json
import pathlib
import urllib.parse
import requests
import sys
import secrets

ROOT = pathlib.Path(__file__).resolve().parent

def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python oauth_catcher.py <hi|te>")
    channel = sys.argv[1]

    client_file = ROOT / "client_secret.json"
    if not client_file.exists():
        sys.exit(f"ERROR: {client_file} not found")

    with open(client_file) as f:
        raw = json.load(f)
    config = raw.get("installed") or raw.get("web")
    if not config:
        sys.exit("ERROR: client_secret.json has unexpected format")

    client_id = config["client_id"]
    client_secret = config["client_secret"]
    state = secrets.token_urlsafe(16)

    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"client_id={client_id}"
        f"&redirect_uri=http://localhost"
        f"&scope=https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.upload"
        f"&response_type=code&access_type=offline&prompt=consent&state={state}"
    )

    print("\n" + "=" * 70)
    print("STEP 1: Copy this URL and paste it into your browser")
    print("=" * 70)
    print(auth_url)
    print("\n" + "=" * 70)
    print("STEP 2: Log in -> Advanced -> Go to shorts-engine (unsafe) -> Allow")
    print("=" * 70)
    print("\n" + "=" * 70)
    print("STEP 3: Browser will show an error page (THIS IS NORMAL)")
    print("        Copy the ENTIRE URL from the address bar")
    print("=" * 70)

    redirect_url = input("\nSTEP 4: Paste that URL here:\n> ").strip()

    parsed = urllib.parse.urlparse(redirect_url)
    query = urllib.parse.parse_qs(parsed.query)

    if "code" not in query:
        sys.exit("ERROR: No 'code' found in URL")

    code = query["code"][0]
    print("\nExchanging code for tokens...")

    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": "http://localhost",
            "grant_type": "authorization_code",
        },
    )

    if r.status_code != 200:
        sys.exit(f"ERROR {r.status_code}: {r.text}")

    tokens = r.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        sys.exit("ERROR: No refresh_token. Revoke access and retry")

    tokens_dir = ROOT / "tokens"
    tokens_dir.mkdir(exist_ok=True)
    token_file = tokens_dir / f"yt_{channel}.json"
    token_data = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": [
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.upload",
        ],
    }
    token_file.write_text(json.dumps(token_data))
    print(f"\nSUCCESS: saved tokens/yt_{channel}.json")

if __name__ == "__main__":
    main()