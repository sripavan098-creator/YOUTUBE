import json
import pathlib
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python -m pipeline.auth <hi|te|en>")
    channel = sys.argv[1]

    flow = InstalledAppFlow.from_client_secrets_file(
        str(ROOT / "client_secret.json"), scopes=SCOPES)

    # Force port 8080, which Codespaces handles perfectly
    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        sys.exit("no refresh_token returned — revoke the app's access and retry")

    (ROOT / "tokens").mkdir(exist_ok=True)
    (ROOT / "tokens" / f"yt_{channel}.json").write_text(json.dumps({
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": SCOPES,
    }), encoding="utf-8")

    print(f"✅ SUCCESS: saved tokens/yt_{channel}.json")
    print("Confirm you signed in as the RIGHT channel — this token uploads to it.")

if __name__ == "__main__":
    main()
