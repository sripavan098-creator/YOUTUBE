import os, re, pathlib, requests
from dotenv import load_dotenv
ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

def pick(ids, prefs, contains=None):
    for p in prefs:
        if p in ids: return p
    if contains:
        c = [i for i in ids if contains in i]
        if c: return sorted(c)[-1]
    return ids[0] if ids else None

gm = em = None
try:
    r = requests.get("https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}, timeout=30)
    r.raise_for_status()
    g = [m["id"] for m in r.json().get("data", [])]
    gm = pick(g, ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"], "llama")
    print("GROQ available:", g)
    print("GROQ picked:", gm)
except Exception as ex:
    print("GROQ probe FAILED:", ex)

try:
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        params={"pageSize": 200}, timeout=30)
    r.raise_for_status()
    e = [m["name"].split("/")[-1] for m in r.json().get("models", [])
         if "generateContent" in m.get("supportedGenerationMethods", [])]
    clean = [m for m in e if not any(x in m for x in ("tts","image","embedding","aqa","imagen","live","audio"))]
    em = pick(clean, ["gemini-3.8-flash","gemini-3.5-flash-lite","gemini-3.5-flash","gemini-3-flash","gemini-2.5-flash"], "flash")
    print("GEMINI available:", e)
    print("GEMINI picked:", em)
except Exception as ex:
    print("GEMINI probe FAILED:", ex)

cfg = (ROOT / "config.yaml").read_text(encoding="utf-8")
if gm: cfg = re.sub(r"model_primary:.*", f"model_primary: {gm}", cfg)
if em: cfg = re.sub(r"model_fallback:.*", f"model_fallback: {em}", cfg)
(ROOT / "config.yaml").write_text(cfg, encoding="utf-8")
print("config.yaml updated.")
