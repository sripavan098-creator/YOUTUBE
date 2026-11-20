import datetime
import pathlib
import sys
import time

import schedule
import yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from pipeline import (db, publish_ig, publish_yt, refresh_ig, render, review,  # noqa: E402
                      scripts, sources, visuals, voice, longform)

CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

# Angle generation costs one LLM call per story, so generate for a wider pool than we
# need: skipped or failed stories must not leave a channel short of its 4 videos.
ANGLE_POOL = 4


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
            if audience == "south_india":
                return (story.get("fits_south", False), story["score"])
            return (story.get("fits_india", False), story["score"])
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


def morning():
    day = datetime.date.today().isoformat()
    channels = CFG["channels"]
    langs = [c["lang"] for c in channels.values()]

    fresh = [s for s in sources.top_stories(20)
             if not any(db.seen(ch, s["url"]) for ch in channels)]
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
            layout = scripts.pick_layout(recent, CFG["layouts"])
            recent.append(layout)
            try:
                shots = visuals.fetch_shots(angle["shots"], ROOT / "out" / f"shots_{sid}_{channel}")
                mp3 = ROOT / "out" / f"{sid}_{channel}.mp3"
                wj = ROOT / "out" / f"{sid}_{channel}.json"
                (ROOT / "out").mkdir(exist_ok=True)
                duration = voice.synth(angle[lcfg["lang"]]["script"], lcfg["voice"],
                                       lcfg["rate"], str(mp3), str(wj))
                video = render.render(sid, channel, lcfg, angle[lcfg["lang"]], str(mp3),
                                      str(wj), duration, shots, layout)
                try:
                    vid_id, slot, privacy = publish_yt.upload(
                        channel, lcfg, CFG["yt_step_min"], i, _clean_dict(angle[lcfg["lang"]]), video,
                        story["url"], CFG.get("yt_public_after_audit", False))
                    print(f"YT {channel} {vid_id} {privacy} {slot}")
                except Exception as e:
                    vid_id, privacy = None, "private"
                    print(f"YT upload failed {channel}: {e} (video kept in out/)")
                db.set_produced(sid, layout, angle["angle_id"], video, vid_id, privacy)
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
        "SELECT id, channel, video_path FROM stories WHERE day=? AND status='done' "
        "AND video_path IS NOT NULL ORDER BY id", (day,)).fetchall()

    # Round-robin by channel, then trim to the daily cap.
    buckets = {ch: [r for r in rows if r[1] == ch] for ch in channels}
    interleaved = []
    while any(buckets.values()):
        for ch in channels:
            if buckets[ch]:
                interleaved.append(buckets[ch].pop(0))

    for n, (sid, channel, path) in enumerate(interleaved[:len(slots)]):
        db.queue_ig(sid, channel, path, f"#shorts #{channel}", slots[n])
    print(f"IG: queued {min(len(interleaved), len(slots))} posts")


def pump_ig():
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for row_id, sid, channel, path, caption in db.due_ig(now):
        try:
            publish_ig.publish(channel, path, caption, f"{sid}_{channel}.mp4")
            db.mark_ig(row_id, "done")
            print(f"IG posted story {sid} on {channel}")
        except Exception as e:
            db.mark_ig(row_id, "failed")
            print(f"IG failed story {sid}: {e}")


def main():
    if "--now" in sys.argv:
        morning()
    elif "--ig" in sys.argv:
        pump_ig()
    elif "--longform" in sys.argv:
        longform.build_all()
    elif "--replay" in sys.argv:
        from pipeline import replay
        replay.replay_all()
    else:
        schedule.every().day.at("06:00").do(morning)
        schedule.every().tuesday.at("10:00").do(longform.build_all)
        schedule.every().friday.at("10:00").do(longform.build_all)
        schedule.every(15).minutes.do(pump_ig)
        schedule.every(25).days.at("09:00").do(refresh_ig.main)
        print("daemon up:", schedule.next_run())
        while True:
            schedule.run_pending()
            time.sleep(30)


if __name__ == "__main__":
    main()
