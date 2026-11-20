import json
import os
import random
import re
import pathlib

import requests
from openai import OpenAI

ROOT = pathlib.Path(__file__).resolve().parent.parent

SYS_ANGLES = """You are a top-tier Indian tech YouTuber. For the SOURCE story, propose 3 DISTINCT angles.

Return STRICT JSON:
{
  "angles": [
    {"angle_id": "A", "take": "one-line unique take", "shots": ["4 English stock-footage keywords"],
     "hi": {"title": "...", "script": "...", "hashtags": ["#AI", "#TechNews", "#shorts"]},
     "te": {"title": "...", "script": "...", "hashtags": ["..."]}},
    {"angle_id": "B", ...}, {"angle_id": "C", ...}
  ]
}

RULES FOR SCRIPT (CRITICAL):
1. HOOK: First sentence MUST be under 8 words. Shocking, curious, or direct. NO "Namaste", NO "Welcome", NO "Today we will talk about".
2. LANGUAGE: Write EXACTLY like a normal person talking to a friend at a chai tapri. Use simple, conversational Hindi/Telugu.
3. TRANSLITERATION: Use English tech words written in native script (e.g., in Hindi: "एआई", "गूगल", "स्मार्टफोन").
4. LENGTH: 70-90 words MAX. Short, punchy sentences. End with a question.
5. NO FLUFF: Never invent facts.

Return ONLY raw JSON. No markdown, no code fences."""

def _extract_json(text):
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(t[start:end + 1])


def _salvage_angles(text):
    """Recover complete angle objects from truncated JSON output."""
    i = text.find('"angles"')
    if i == -1:
        return []
    j = text.find("[", i)
    if j == -1:
        return []
    out, depth, start = [], 0, None
    for k in range(j + 1, len(text)):
        ch = text[k]
        if ch == "{":
            if depth == 0:
                start = k
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    out.append(json.loads(text[start:k + 1]))
                except Exception:
                    pass
                start = None
    return out

def _groq(prompt, model):
    c = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1", timeout=60)
    kwargs = {}
    if "gpt-oss" in model:
        kwargs["extra_body"] = {"reasoning_effort": "low"}
    r = c.chat.completions.create(
        model=model, temperature=0.7, max_tokens=8000,
        messages=[{"role": "system", "content": SYS_ANGLES},
                  {"role": "user", "content": prompt}], **kwargs)
    return r.choices[0].message.content

def _gemini(prompt, model):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": SYS_ANGLES + "\n\n" + prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}},
        timeout=40)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def _check(angles, langs):
    """Return None if usable, otherwise the exact reason it was rejected."""
    if not isinstance(angles, list):
        return "angles is not a list"
    if len(angles) < 2:
        return f"only {len(angles)} angles (need >=2)"
    seen = set()
    for i, a in enumerate(angles):
        if not isinstance(a, dict):
            return f"angle {i} is not an object"
        if len(a.get("shots", [])) < 3:
            return f"angle {i} has {len(a.get('shots', []))} shots (need >=3)"
        take = str(a.get("take", "")).strip().lower()
        if not take:
            return f"angle {i} has empty take"
        if take in seen:
            return f"angle {i} duplicate take"
        seen.add(take)
        for lang in langs:
            blk = a.get(lang)
            if not isinstance(blk, dict):
                return f"angle {i} missing '{lang}' object"
            n = len(str(blk.get("script", "")).split())
            if n < 20:
                return f"angle {i} '{lang}' script only {n} words (need >=20)"
            if not blk.get("title"):
                return f"angle {i} '{lang}' missing title"
            if not blk.get("hashtags"):
                return f"angle {i} '{lang}' missing hashtags"
    return None

def _dump(tag, text):
    try:
        d = ROOT / "out" / "debug"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{tag}.txt"
        f.write_text(text or "", encoding="utf-8")
        return str(f)
    except Exception:
        return "(dump failed)"

def propose_angles(story, cfg):
    langs = [c["lang"] for c in cfg["channels"].values()]
    prompt = f"TITLE: {story['title']}\nSOURCE_URL: {story['url']}\nSOURCE:\n{story['body']}"
    providers = [(_groq, cfg["model_primary"]), (_gemini, cfg["model_fallback"])]
    if cfg.get("model_fallback2"):
        providers.append((_gemini, cfg["model_fallback2"]))
    errors = []
    slug = re.sub(r"[^a-z0-9]+", "_", story["title"].lower())[:40]
    for fn, model in providers:
        for attempt in range(1):
            raw = ""
            try:
                print(f'  trying {model}...', flush=True)
                raw = fn(prompt, model)
                try:
                    angles = _extract_json(raw).get("angles", [])
                except json.JSONDecodeError:
                    angles = _salvage_angles(raw)
                    print(f"    salvaged {len(angles)} complete angles from truncated JSON", flush=True)
                reason = _check(angles, langs)
                if reason is None:
                    angles = angles[:3]
                    for i, a in enumerate(angles):
                        a.setdefault("angle_id", chr(65 + i))
                    return angles
                path = _dump(f"{slug}_{model.replace('/', '-')}_{attempt}", raw)
                errors.append(f"{model}: {reason} [raw: {path}]")
            except Exception as e:
                if raw:
                    _dump(f"{slug}_{model.replace('/', '-')}_{attempt}", raw)
                errors.append(f"{model}: {e}")
    raise RuntimeError("angle generation failed -> " + " | ".join(errors))

def pick_layout(used_recently, layouts):
    """Rotate layouts so one channel does not look templated from video to video."""
    available = [l for l in layouts if l not in used_recently[-3:]]
    return random.choice(available or layouts)
