import socket, time, pathlib, yaml
socket.setdefaulttimeout(25)
from dotenv import load_dotenv
ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
from pipeline import sources, scripts
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

t = time.time()
print("fetching feeds...", flush=True)
stories = sources.top_stories(3)
print(f"feeds done in {time.time()-t:.1f}s -> {len(stories)} stories", flush=True)

s = stories[0]
print("story:", s["title"], flush=True)
t = time.time()
try:
    angles = scripts.propose_angles(s, CFG)
    print(f"ANGLES OK in {time.time()-t:.1f}s -> {len(angles)} angles", flush=True)
    for a in angles:
        print(" ", a["angle_id"], a["take"][:70],
              "| hi words:", len(a["hi"]["script"].split()),
              "| te words:", len(a["te"]["script"].split()), flush=True)
except Exception as e:
    print(f"FAILED after {time.time()-t:.1f}s: {e}", flush=True)
