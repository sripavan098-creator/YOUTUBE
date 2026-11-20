"""Live smoke test: real feeds, real model call.

    python -m pipeline.probe
"""

import pathlib
import socket
import sys
import time

import yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    socket.setdefaulttimeout(25)
    load_dotenv(ROOT / ".env")

    from pipeline import scripts, sources

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

    t = time.time()
    print("fetching feeds...", flush=True)
    stories = sources.top_stories(3)
    print(f"feeds done in {time.time() - t:.1f}s -> {len(stories)} stories", flush=True)
    if not stories:
        print("no stories returned; feeds or network are down")
        return 1

    s = stories[0]
    print("story:", s["title"], flush=True)
    t = time.time()
    try:
        angles = scripts.propose_angles(s, cfg)
        print(f"ANGLES OK in {time.time() - t:.1f}s -> {len(angles)} angles", flush=True)
        for a in angles:
            print(" ", a["angle_id"], a["take"][:70], flush=True)
        return 0
    except Exception as e:
        print(f"FAILED after {time.time() - t:.1f}s: {e}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
