import json
import os
import random

import requests
from openai import OpenAI

SYS_ANGLES = """You are the editor of a tech-news channel. For the SOURCE story, propose 3
DISTINCT angles. Each angle needs its own hook, framing and closing question - they are
NOT translations of one another.

Return STRICT JSON:
{
  "angles": [
    {"angle_id": "A",
     "take": "one-line unique take",
     "shots": ["4 English stock-footage keywords"],
     "hi": {"title": "...", "script": "...", "hashtags": ["#AI", "#TechNews", "#shorts"]},
     "te": {"title": "...", "script": "...", "hashtags": ["..."]}},
    {"angle_id": "B", ...},
    {"angle_id": "C", ...}
  ]
}

Use ONLY facts present in SOURCE. Never invent specs, prices, dates, quotes or numbers.
If SOURCE lacks a detail, omit it rather than guessing.

Per language object:
- title: <=60 characters, factual, curious without lying, in that language's script.
- script: 85-110 words. First sentence is a hook of 8 words or fewer: no greeting, no
  "welcome back", no channel name. End with a short question.
- hashtags: 3-5 tags including #shorts.

hi: natural spoken Hindi in Devanagari. Transliterate tech terms (एआई, गूगल, जीपीयू).
te: natural spoken Telugu in Telugu script. Transliterate tech terms (ఏఐ, గూగుల్).
Both must sound like a person talking to a friend, not a translation of English.

The three angles MUST differ in framing: for example consumer impact vs industry impact
vs technical deep-dive, or Indian-market vs global, or pro vs con.
"""


def _groq(prompt, model):
    c = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1")
    r = c.chat.completions.create(
        model=model, temperature=0.8, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYS_ANGLES},
                  {"role": "user", "content": prompt}])
    return r.choices[0].message.content


def _gemini(prompt, model):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": SYS_ANGLES + "\n\n" + prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}},
        timeout=120)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _valid(angles, langs):
    if not isinstance(angles, list) or len(angles) != 3:
        return False
    seen_takes = set()
    for a in angles:
        if len(a.get("shots", [])) < 3:
            return False
        take = str(a.get("take", "")).strip().lower()
        if not take or take in seen_takes:
            return False
        seen_takes.add(take)
        for lang in langs:
            blk = a.get(lang)
            if not isinstance(blk, dict):
                return False
            if len(str(blk.get("script", "")).split()) < 60:
                return False
            if not blk.get("title") or not blk.get("hashtags"):
                return False
    return True


def propose_angles(story, cfg):
    langs = [c["lang"] for c in cfg["channels"].values()]
    prompt = f"TITLE: {story['title']}\nSOURCE_URL: {story['url']}\nSOURCE:\n{story['body']}"
    errors = []
    for fn, model in ((_groq, cfg["model_primary"]), (_gemini, cfg["model_fallback"])):
        try:
            data = json.loads(fn(prompt, model))
            angles = data.get("angles", [])
            if _valid(angles, langs):
                for i, a in enumerate(angles):
                    a.setdefault("angle_id", chr(65 + i))
                return angles
            errors.append(f"{model}: failed validation")
        except Exception as e:
            errors.append(f"{model}: {e}")
    raise RuntimeError("angle generation failed -> " + " | ".join(errors))


def pick_layout(used_recently, layouts):
    """Rotate layouts so one channel does not look templated from video to video."""
    available = [l for l in layouts if l not in used_recently[-3:]]
    return random.choice(available or layouts)
