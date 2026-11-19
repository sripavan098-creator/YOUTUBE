"""Preflight: report every missing prerequisite before the first batch runs.

    python -m pipeline.doctor
"""

import os
import pathlib
import shutil
import subprocess
import sys

import yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

REQUIRED_ENV = ["GROQ_API_KEY", "GEMINI_API_KEY", "PEXELS_API_KEY",
                "TG_BOT_TOKEN", "TG_CHAT_ID", "GH_TOKEN", "GH_REPO",
                "IG_APP_ID", "IG_APP_SECRET", "IG_REDIRECT"]


def _check(label, ok, detail=""):
    print(f"[{'OK ' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


def _esbuild_ok():
    try:
        out = subprocess.run(["node", "-e", "console.log(require('esbuild').version)"],
                             cwd=str(ROOT / "remotion"), capture_output=True,
                             text=True, timeout=60)
        return out.returncode == 0 and out.stdout.strip() != ""
    except Exception:
        return False


def _telegram_ok():
    import requests
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN']}/getMe",
            timeout=20).json()
        return bool(r.get("ok"))
    except Exception:
        return False


def main():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    results = []

    results.append(_check("config.yaml parses", bool(cfg.get("channels"))))
    results.append(_check("client_secret.json present",
                          (ROOT / "client_secret.json").exists(),
                          "Desktop OAuth client from Google Cloud"))

    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    results.append(_check(".env keys", not missing,
                          ("missing: " + ", ".join(missing)) if missing else "all set"))

    for ch in cfg.get("channels", {}):
        results.append(_check(f"tokens/yt_{ch}.json",
                              (ROOT / "tokens" / f"yt_{ch}.json").exists(),
                              f"run: python -m pipeline.auth {ch}"))
        results.append(_check(f"tokens/ig_{ch}.json",
                              (ROOT / "tokens" / f"ig_{ch}.json").exists(),
                              f"run: python -m pipeline.auth_ig {ch} <CODE>"))

    results.append(_check("node/npx on PATH",
                          shutil.which("npx") is not None or shutil.which("npx.cmd") is not None))
    results.append(_check("remotion node_modules",
                          (ROOT / "remotion" / "node_modules").exists(),
                          "cd remotion && npm install"))
    results.append(_check("esbuild binary works", _esbuild_ok(),
                          "cd remotion && npm rebuild esbuild"))
    results.append(_check("Telegram reachable", _telegram_ok()))

    if all(results):
        print("\nAll checks passed - run: python -m pipeline.main --now")
        return 0
    print(f"\n{results.count(False)} check(s) failed. Fix these before going live.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
