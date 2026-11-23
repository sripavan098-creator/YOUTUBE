import datetime
import json
import pathlib
import random
import shutil
import subprocess

import yaml
from mutagen.mp3 import MP3

from pipeline import db, publish_yt, render, visuals, voice
from pipeline.render import npx_bin

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

LONGFORM_SYS = """You write a 6-8 minute YouTube script that CONNECTS this week's stories
into one narrative. This is ORIGINAL commentary, not a summary: find the theme that ties
the stories together and make an argument about where tech is heading.

Return STRICT JSON:
{"theme": "one-line thesis",
 "title": "<=70 chars, curious not clickbait",
 "script": "800-1100 words: hook (1 para), context (2 para), three story deep-dives with
            your own take (6 para), forward look (2 para). No 'welcome back' filler.",
 "shots": ["8 English stock-footage keywords matching the theme"],
 "hashtags": ["#tech", "#commentary", "#ai"]}

Use only facts present in the supplied headlines. Do not invent numbers or quotes."""


def _llm(prompt):
    from openai import OpenAI
    from pipeline.provider_keys import groq_keys
    from pipeline.scripts import _gemini

    def groq_call(m):
        last_error = None
        for index, key in enumerate(groq_keys()):
            try:
                result = OpenAI(
                    api_key=key,
                    base_url="https://api.groq.com/openai/v1",
                ).chat.completions.create(
                    model=m,
                    temperature=0.8,
                    response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": LONGFORM_SYS},
                              {"role": "user", "content": prompt}],
                ).choices[0].message.content
                if index:
                    print("  Groq backup key succeeded")
                return result
            except Exception as error:
                last_error = error
                if index + 1 < len(groq_keys()):
                    print(f"  Groq key {index + 1} failed, trying backup key...")
                    continue
                raise
        raise last_error

    for model, call in (
        (CFG["model_primary"], groq_call),
        (CFG["model_fallback"], lambda m: _gemini(
            LONGFORM_SYS, prompt, m, temperature=0.8, timeout=180)),
    ):
        try:
            data = json.loads(call(model))
            if data.get("script") and len(data["script"].split()) >= 600:
                return data
        except Exception as e:
            print(f"longform {model} failed: {e}")
    raise RuntimeError("longform script generation failed")


def _built_this_week(channel):
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    return db.count_longform(channel, week_ago)


def build_for_channel(channel):
    lcfg = CFG["channels"][channel]
    since = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
    items = db.week_stories(since, channel)
    if len(items) < 4:
        print(f"longform {channel}: only {len(items)} stories, need 4")
        return

    titles = "\n".join(f"- {t}" for _, _, t in items)
    script = _llm(f"This week's stories on the {channel} channel:\n{titles}\n\n"
                  f"Write one long-form video tying them together.")

    stamp = datetime.date.today().isoformat()
    mp3 = ROOT / "out" / f"long_{channel}_{stamp}.mp3"
    words = ROOT / "out" / f"long_{channel}_{stamp}.json"
    (ROOT / "out").mkdir(exist_ok=True)

    duration = voice.synth(script["script"], lcfg["voice"], lcfg["rate"], str(mp3), str(words))
    shots = visuals.fetch_shots(script["shots"], ROOT / "out" / f"shots_long_{channel}_{stamp}")
    video = render.render(f"long_{stamp}", channel, lcfg, script, str(mp3), str(words),
                          duration, shots, layout="explainer")

    vid_id, slot, privacy = publish_yt.upload(
        channel, lcfg, 0, 0, script, video, "https://youtube.com",
        CFG.get("yt_public_after_audit", False))
    db.add_longform(channel, stamp, vid_id, video)
    print(f"longform {channel}: {vid_id} ({privacy}) slot {slot}")


def build_all():
    today = datetime.date.today().isoformat()
    for channel in CFG["channels"]:
        if db.built_longform_today(channel, today):
            print(f"longform {channel}: already built today, skipping")
            continue
        if _built_this_week(channel) >= CFG["longform_per_week"]:
            print(f"longform {channel}: already at {CFG['longform_per_week']}/week")
            continue
        try:
            build_for_channel(channel)
        except Exception as e:
            print(f"longform {channel} failed: {e}")
