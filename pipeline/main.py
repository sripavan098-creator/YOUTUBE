import datetime
import json
import pathlib

import os
import re

# Robust .env loader for Python 3.14 compatibility
_env_path = pathlib.Path(__file__).parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

def _sanitize_metadata(obj):
    if isinstance(obj, dict):
        return {k: _sanitize_metadata(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_metadata(v) for v in obj]
    elif isinstance(obj, str):
        obj = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', obj)
        obj = obj.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        obj = re.sub(r'\s+', ' ', obj).strip()
        return obj
    return obj

import sys
import time

import schedule
import yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from pipeline import (audio, db, publish_ig, publish_yt, refresh_ig, render, review,  # noqa: E402
                      learn, scripts, sources, timing, trends, visuals, voice, longform,
                      langfix, motion)

def _clean_dict(script):
    """Bulletproof sanitizer: Nukes ALL control characters from metadata."""
    def nuke(obj):
        if isinstance(obj, dict):
            return {k: nuke(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [nuke(v) for v in obj]
        elif isinstance(obj, str):
            # Nuke ALL control characters except newlines in descriptions
            cleaned = ""
            for ch in obj:
                code = ord(ch)
                if code < 32 and code not in (10, 13):  # keep \n and \r
                    continue
                if 127 <= code <= 159:
                    continue
                cleaned += ch
            return cleaned.strip()
        return obj
    
    out = nuke({k: v for k, v in script.items() if k != "description"})
    if script.get("description"):
        out["description"] = nuke(script["description"])
    return out


CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

from pipeline import ig_once as _ig_once  # noqa: E402
_ig_once.install(db, publish_ig)


# Angle generation costs one LLM call per story, so generate for a wider pool than we
# need: skipped or failed stories must not leave a channel short of its 4 videos.
ANGLE_POOL = 4

# Slot offset per batch:
# batch 0 (morning)   → slot_offset=0  → yt_start   (08:30)
# batch 1 (lunch)     → slot_offset=1  → yt_start_2 (13:00)
# batch 2 (post-work) → slot_offset=2  → yt_start_3 (18:00)
# batch 3 (night)     → slot_offset=3  → yt_start_4 (21:00)
# The offset is passed to publish_yt._slot(index=slot_offset+i) so the index
# modulo the number of configured slots picks the right time key.
_STORIES = CFG.get("stories_per_channel", 4)
_SPD = CFG.get("shorts_per_day", 2)   # 4 → 4 batches/day


def _ig_slots(day, count, start_hour=12, end_hour=21):
    """Spread posts across the day, dropping slots that have already passed so a
    late-morning run does not dump the whole queue at once."""
    if count <= 0:
        return []
    now = datetime.datetime.now()
    span = (end_hour - start_hour) * 60
    step = span / count if count > 1 else 0
    out = []
    for i in range(count):
        minutes = start_hour * 60 + int(step * i)
        slot = f"{day}T{minutes // 60:02d}:{minutes % 60:02d}:00"
        if datetime.datetime.fromisoformat(slot) > now:
            out.append(slot)
    return out


def _assign(picked, channels):
    """Give each channel its best-fit stories, allowing a story to serve both channels.

    A story covered by both channels uses a different angle on each, so the two videos
    are genuinely different pieces rather than one script in two languages.
    """
    per = CFG["stories_per_channel"]
    assigned = {ch: [] for ch in channels}

    # Least-flexible channel first: South-India fits are scarcer than India fits,
    # so claim those before the broader channel consumes the pool.
    order = sorted(channels, key=lambda c: 0 if channels[c]["audience"] == "south_india" else 1)

    for ch in order:
        audience = channels[ch]["audience"]
        def fit(item):
            story, _ = item
            relevance = story.get("channel_scores", {}).get(ch, 0)
            if audience == "south_india":
                return (story.get("fits_south", False), relevance, story["score"])
            return (story.get("fits_india", False), relevance, story["score"])
        for story, angles in sorted(picked, key=fit, reverse=True):
            if len(assigned[ch]) >= per:
                break
            if any(s["url"] == story["url"] for s, _ in assigned[ch]):
                continue
            assigned[ch].append((story, angles))
    return assigned


def _angle_for(channel, channels, chosen, all_angles, shared):
    """The editor's pick is final unless both channels take this story.

    A shared story is published on each channel with a different angle, so the two
    videos are genuinely different pieces rather than one script in two languages.
    """
    if not shared:
        return chosen
    order = sorted(channels, key=lambda c: 0 if channels[c]["audience"] == "south_india" else 1)
    i = next((n for n, a in enumerate(all_angles) if a["angle_id"] == chosen["angle_id"]), 0)
    return all_angles[(i + order.index(channel)) % len(all_angles)]


def _gap_after_hook(script):
    """Silence the voice engine puts after the hook (owned by beat 0, not spoken)."""
    nxt = script["beats"][1].get("role", "fact") if len(script["beats"]) > 1 else "fact"
    return voice.GAP_BEFORE.get(nxt, 0.1)


def _recent_archetypes(channel, n=3):
    rows = db.DB.execute("SELECT archetype FROM stories WHERE channel=? AND archetype IS NOT NULL "
                         "ORDER BY id DESC LIMIT ?", (channel, n)).fetchall()
    return [r[0] for r in reversed(rows)]


def _tokens(t):
    return {w for w in re.findall(r"[a-z0-9]{3,}", t.lower())}


def _repeats_recent(channel, story, threshold=0.6):
    """True when this story is the same topic as something the channel made in the last two
    weeks (different outlet, same news). Repetition is what gets a channel judged as
    mass-produced, and viewers do not need the same video twice."""
    mine = _tokens(story["title"])
    if len(mine) < 3:
        return False
    for t in db.recent_titles(channel):
        other = _tokens(t)
        if other and len(mine & other) / len(mine | other) >= threshold:
            return True
    return False


def _channel_filter_from_args(args):
    raw = None
    for index, arg in enumerate(args):
        if arg == "--only":
            if index + 1 >= len(args) or args[index + 1].startswith("--"):
                raise SystemExit("--only requires a comma-separated channel list (for example: te)")
            raw = args[index + 1]
            break
        if arg.startswith("--only="):
            raw = arg.split("=", 1)[1]
            break
    if raw is None:
        return None
    channels = {channel.strip() for channel in raw.split(",") if channel.strip()}
    if not channels:
        raise SystemExit("--only requires at least one channel")
    unknown = channels - CFG["channels"].keys()
    if unknown:
        raise SystemExit("unknown channel selection: " + ", ".join(sorted(unknown)))
    return channels


def morning(slot_offset: int = 0, only_channels=None):
    """Run one production batch, optionally restricted to selected channels.

    publish_yt._slot() maps (slot_offset + i) % num_configured_slots to one of
    yt_start / yt_start_2 / yt_start_3 / yt_start_4.

    With 2 channels x 4 slots = 8 YT Shorts per day -> 240 in 30 days.
    """
    day = datetime.date.today().isoformat()
    channels = {
        channel: settings for channel, settings in CFG["channels"].items()
        if only_channels is None or channel in only_channels
    }
    langs = [c["lang"] for c in channels.values()]

    trend_items = trends.fetch_all(CFG) if CFG.get("trends", True) else []
    fresh = [s for s in sources.top_stories(20, trend_items=trend_items, channels=channels)
             if not any(db.seen(ch, s["url"]) for ch in channels)
             and not all(_repeats_recent(ch, s) for ch in channels)]
    if not fresh:
        print("no new stories")
        return

    pairs = []
    for story in fresh[:ANGLE_POOL]:
        try:
            pairs.append((story, scripts.propose_angles(story, CFG)))
        except Exception as e:
            print(f"angles failed: {story['title'][:60]} -> {e}")

    if not pairs:
        print("no angles generated")
        return

    picked = review.review(pairs)
    if not picked:
        print("everything skipped")
        return

    assigned = _assign(picked, channels)

    # The full angle list per story, so a shared story can use a different angle on
    # each channel even though review() returned only the editor's pick.
    all_angles = {story["url"]: angles for story, angles in pairs}
    takes = {}
    for items in assigned.values():
        for story, _ in items:
            takes[story["url"]] = takes.get(story["url"], 0) + 1

    for channel, items in assigned.items():
        lcfg = channels[channel]
        recent = db.recent_layouts(channel)
        for i, (story, chosen) in enumerate(items):
            angle = _angle_for(channel, channels, chosen, all_angles[story["url"]],
                               shared=takes[story["url"]] > 1)
            sid = db.add_story(day, channel, story["url"], story["title"], story["body"])
            try:
                # Stage 2: write the picked angle natively for THIS channel, then voice it.
                # The spoken hook must land within 2.8 s. TTS length can only be known after
                # synthesis, so an overlong hook is rewritten once using its measured length.
                (ROOT / "out").mkdir(exist_ok=True)
                raw_mp3 = ROOT / "out" / f"{sid}_{channel}.raw.mp3"
                mp3 = ROOT / "out" / f"{sid}_{channel}.mp3"
                wj = ROOT / "out" / f"{sid}_{channel}.json"
                note = ""
                archetype = learn.pick_archetype(channel, _recent_archetypes(channel))
                print(f"  hook archetype: {archetype}")
                for attempt in range(2):
                    script = scripts.write_script(story, angle, lcfg, CFG, note=note,
                                                  archetype=archetype)
                    # every beat is voiced on its own with its mood, then stitched with
                    # deliberate pauses, so beat times are exact (no estimating from words)
                    words, beats, duration = voice.synth_beats(
                        script["beats"], lcfg, ROOT / "out" / f"vo_{sid}_{channel}", raw_mp3)
                    wj.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
                    hook_s = beats[0][1] - _gap_after_hook(script)
                    if hook_s <= scripts.HOOK_MAX_SECONDS:
                        break
                    if attempt == 1:
                        raise RuntimeError(
                            f"hook is {hook_s:.2f}s after rewrite "
                            f"(maximum {scripts.HOOK_MAX_SECONDS}s)"
                        )
                    note = (f"Your first line took {hook_s:.2f} seconds to speak. Rewrite "
                            f"the script with a hook of at most {scripts.HOOK_MAX_WORDS} "
                            f"short words that fits within {scripts.HOOK_MAX_SECONDS} seconds.")
                    print(f"  hook {hook_s:.1f}s too slow, rewriting once")
                layout = scripts.pick_layout(recent, CFG["layouts"],
                                              preferred=script.get("story_format"))
                recent.append(layout)
                shots = visuals.fetch_shots(script["shots"], ROOT / "out" / f"shots_{sid}_{channel}")
                starts = [s for s, _ in beats]
                cues = audio.default_cues(starts, [b["role"] for b in script["beats"]])
                for b, (st, _e) in zip(script["beats"], beats):
                    if b.get("slam") or b.get("stat"):
                        cues.append((st + 0.2, "pop"))
                duration = audio.finish(raw_mp3, mp3, starts, duration,
                                        sfx=CFG.get("sfx", True),
                                        music_volume=CFG.get("music_volume", 0.16), cues=cues)
                enhanced_mp3 = ROOT / "out" / f"{sid}_{channel}.enhanced.mp3"
                final_mp3 = motion.enhance_audio(
                    mp3, starts, enhanced_mp3,
                    music_dir=str(ROOT / "assets" / "music"),
                )
                if final_mp3 != mp3:
                    mp3 = pathlib.Path(final_mp3)
                langfix.audio_gate(str(mp3), script["script"], lcfg["lang"])
                video, thumbnail, ig_cover = render.render(sid, channel, lcfg, script, str(mp3), str(wj),
                                                duration, shots, layout, beats=beats)
                # Persist the generated metadata next to the mp4 so a later batch
                # upload can reuse it instead of guessing from the filename.
                (ROOT / "out" / f"{sid}_{channel}.meta.json").write_text(
                    json.dumps({"title": script["title"],
                                "description": script.get("description") or script["script"].split(".")[0],
                                "hashtags": script["hashtags"], "tags": script.get("tags", []),
                                "search_terms": script.get("search_terms", []),
                                "archetype": archetype,
                                "story_format": script.get("story_format", "explainer")},
                       ensure_ascii=False),
                    encoding="utf-8")
                try:
                    vid_id, slot, privacy = publish_yt.upload(
                        channel, lcfg, CFG["yt_step_min"], slot_offset + i,
                        _clean_dict(script), video,
                        story["url"], CFG.get("yt_public_after_audit", False),
                        thumbnail=thumbnail)
                    print(f"YT {channel} {vid_id} {privacy} {slot}")
                    # upload_batch.py checks this marker so it never uploads the same render twice
                    (ROOT / "out" / f"{sid}_{channel}.uploaded.json").write_text(
                        json.dumps({"id": vid_id, "privacy": privacy}), encoding="utf-8")
                except Exception as e:
                    vid_id, privacy = None, "private"
                    print(f"YT upload failed {channel}: {e} (video kept in out/)")
                db.set_archetype(sid, archetype)
                db.set_produced(sid, layout, angle["angle_id"], video, vid_id, privacy)
                db.set_caption(sid, script.get("ig_caption") or f"#shorts #{channel}")
                db.set_status(sid, "done")
            except Exception as e:
                db.set_status(sid, "failed")
                print(f"story {sid}/{channel} failed: {e}")

    _queue_ig(day, channels)


def _queue_ig(day, channels):
    """Queue at most ig_daily videos, alternating channels so neither starves."""
    slots = _ig_slots(day, CFG.get("ig_daily", 3))
    if not slots:
        print("IG: no slots left today, nothing queued")
        return
    rows = db.DB.execute(
        "SELECT id, channel, video_path, ig_caption FROM stories WHERE day=? AND status='done' "
        "AND video_path IS NOT NULL ORDER BY id", (day,)).fetchall()

    # Round-robin by channel, then trim to the daily cap.
    buckets = {ch: [r for r in rows if r[1] == ch] for ch in channels}
    interleaved = []
    while any(buckets.values()):
        for ch in channels:
            if buckets[ch]:
                interleaved.append(buckets[ch].pop(0))

    for n, (sid, channel, path, cap) in enumerate(interleaved[:len(slots)]):
        db.queue_ig(sid, channel, path, cap or f"#shorts #{channel}", slots[n])
    print(f"IG: queued {min(len(interleaved), len(slots))} posts")


def batch1():
    """Lunch batch — targets yt_start_2 (13:00 IST)."""
    if _SPD < 2:
        print("shorts_per_day < 2 — skipping batch1")
        return
    morning(slot_offset=1)


def batch2():
    """Post-work batch — targets yt_start_3 (18:00 IST)."""
    if _SPD < 3:
        print("shorts_per_day < 3 — skipping batch2")
        return
    morning(slot_offset=2)


def batch3():
    """Night batch — targets yt_start_4 (21:00 IST)."""
    if _SPD < 4:
        print("shorts_per_day < 4 — skipping batch3")
        return
    morning(slot_offset=3)


# Keep 'evening' as an alias for the second batch so old CLI flags still work
evening = batch1


def pump_ig():
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for row_id, sid, channel, path, caption in db.due_ig(now):
        try:
            out_dir = ROOT / "out"
            # Prefer the designed IG cover (1080×1920) for Instagram
            ig_cover_path = out_dir / f"{sid}_{channel}_ig_cover.jpg"
            yt_thumb_path = out_dir / f"{sid}_{channel}_thumb.jpg"
            if ig_cover_path.exists():
                thumbnail = str(ig_cover_path)
            elif yt_thumb_path.exists():
                thumbnail = str(yt_thumb_path)
            else:
                thumbnail = None
            publish_ig.publish(channel, path, caption, f"{sid}_{channel}.mp4",
                               thumbnail=thumbnail)
            db.mark_ig(row_id, "done")
            print(f"IG posted story {sid} on {channel}")
        except Exception as e:
            db.mark_ig(row_id, "failed")
            print(f"IG failed story {sid}: {e}")


def main():
    if "--now" in sys.argv:
        morning(only_channels=_channel_filter_from_args(sys.argv[1:]))
    elif "--evening" in sys.argv or "--batch1" in sys.argv:
        batch1()
    elif "--batch2" in sys.argv:
        batch2()
    elif "--batch3" in sys.argv:
        batch3()
    elif "--gallery" in sys.argv:
        from pipeline import gallery
        print(gallery.build())
    elif "--learn" in sys.argv:
        learn.refresh_stats()
    elif "--ig" in sys.argv:
        pump_ig()
    elif "--longform" in sys.argv:
        longform.build_all()
    elif "--replay" in sys.argv:
        from pipeline import replay
        replay.replay_all()
    else:
        # 4-slot render schedule (2h before each posting slot):
        #   06:00 → batch0  → posts at 08:30 (morning commute)
        #   10:30 → batch1  → posts at 13:00 (lunch scroll)
        #   15:30 → batch2  → posts at 18:00 (post-work)
        #   18:30 → batch3  → posts at 21:00 (prime time)
        # Each render takes ~90 min for 2 channels × 4 stories → 2h safety margin.
        schedule.every().day.at("05:30").do(learn.refresh_stats)
        schedule.every().day.at("06:00").do(morning)   # batch 0
        if _SPD >= 2:
            schedule.every().day.at("10:30").do(batch1)  # batch 1
        if _SPD >= 3:
            schedule.every().day.at("15:30").do(batch2)  # batch 2
        if _SPD >= 4:
            schedule.every().day.at("18:30").do(batch3)  # batch 3
        schedule.every().tuesday.at("10:00").do(longform.build_all)
        schedule.every().friday.at("10:00").do(longform.build_all)
        schedule.every(15).minutes.do(pump_ig)
        schedule.every(25).days.at("09:00").do(refresh_ig.main)
        schedules = ["06:00 batch0"]
        if _SPD >= 2: schedules.append("10:30 batch1")
        if _SPD >= 3: schedules.append("15:30 batch2")
        if _SPD >= 4: schedules.append("18:30 batch3")
        print(f"daemon up — {_SPD} batches/day: {', '.join(schedules)} — next: {schedule.next_run()}")
        while True:
            schedule.run_pending()
            time.sleep(30)


if __name__ == "__main__":
    main()