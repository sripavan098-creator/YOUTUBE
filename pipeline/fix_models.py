"""Repoint config.yaml at models the account can actually call.

    python -m pipeline.fix_models            # print what would change
    python -m pipeline.fix_models --write    # rewrite config.yaml

Writes nothing unless --write is passed: importing this module must never touch
config.yaml.
"""

import os
import pathlib
import re
import sys

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Preference order. Anything not returned by the probe is skipped.
GROQ_PREFS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
GEMINI_PREFS = ["gemini-1.5-flash-latest", "gemini-1.5-pro-latest", "gemini-1.0-pro"]


def pick(ids, prefs, contains=None):
    for p in prefs:
        if p in ids:
            return p
    if contains:
        c = [i for i in ids if contains in i]
        if c:
            return sorted(c)[-1]
    return ids[0] if ids else None


def probe_groq():
    from pipeline.provider_keys import groq_keys

    keys = groq_keys()
    if not keys:
        raise RuntimeError("GROQ_API_KEY is not configured")
    last_error = None
    for index, key in enumerate(keys):
        try:
            r = requests.get("https://api.groq.com/openai/v1/models",
                             headers={"Authorization": f"Bearer {key}"},
                             timeout=30)
            r.raise_for_status()
            break
        except Exception as error:
            last_error = error
            if index + 1 < len(groq_keys()):
                print("  Groq key failed, trying backup key...")
                continue
            raise last_error
    ids = [m["id"] for m in r.json().get("data", [])]
    print("GROQ available:", ids)
    return pick(ids, GROQ_PREFS)


def probe_gemini():
    from pipeline.provider_keys import gemini_keys

    keys = gemini_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    for index, key in enumerate(keys):
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                             headers={"x-goog-api-key": key},
                             params={"pageSize": 200}, timeout=30)
            r.raise_for_status()
            if index:
                print("  Gemini backup key succeeded")
            break
        except requests.RequestException:
            if index + 1 == len(keys):
                raise
            print("  Gemini key failed, trying backup key...")
    ids = [m["name"].split("/")[-1] for m in r.json().get("models", [])
           if "generateContent" in m.get("supportedGenerationMethods", [])]
    skip = ("tts", "image", "embedding", "aqa", "imagen", "live", "audio")
    clean = [m for m in ids if not any(x in m for x in skip)]
    print("GEMINI available:", clean)
    return pick(clean, GEMINI_PREFS, "flash")


def main():
    load_dotenv(ROOT / ".env")
    write = "--write" in sys.argv

    changes = {}
    for key, label, fn in (("model_primary", "GROQ", probe_groq),
                           ("model_fallback", "GEMINI", probe_gemini)):
        try:
            picked = fn()
            print(f"{label} picked:", picked)
            if picked:
                changes[key] = picked
        except Exception as ex:
            print(f"{label} probe FAILED: {ex}")

    if not changes:
        print("nothing resolved; config.yaml untouched")
        return 1

    for k, v in changes.items():
        print(f"{k}: {v}")
    if not write:
        print("\nDry run. Re-run with --write to update config.yaml.")
        return 0

    cfg_path = ROOT / "config.yaml"
    cfg = cfg_path.read_text(encoding="utf-8")
    for k, v in changes.items():
        cfg = re.sub(rf"^{k}:.*$", f"{k}: {v}", cfg, flags=re.M)
    cfg_path.write_text(cfg, encoding="utf-8")
    print("config.yaml updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
