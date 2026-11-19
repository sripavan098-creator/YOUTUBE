"""Promote the private backlog to public once the YouTube API audit clears.

This flips the existing uploads with videos.update. It deliberately does NOT
re-upload: a second upload of the same file creates a duplicate video on the
channel, which is the opposite of what an audit review wants to see.
"""

import datetime

from zoneinfo import ZoneInfo

from pipeline import db, publish_yt

IST = ZoneInfo("Asia/Kolkata")


def replay_all():
    backlog = db.private_backlog()
    if not backlog:
        print("nothing to promote")
        return

    import yaml
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))

    now = datetime.datetime.now(IST)
    promoted = 0
    for n, (sid, channel, url, title, video_path) in enumerate(backlog):
        lcfg = cfg["channels"].get(channel)
        if not lcfg:
            continue
        # Spread the promoted videos out instead of dumping them all at once.
        slot = publish_yt._slot(lcfg, cfg["yt_step_min"], n)
        if slot < now + datetime.timedelta(minutes=20):
            slot += datetime.timedelta(days=1)
        video_id = _vid(sid)
        if not video_id:
            print(f"skip story {sid}: no yt_video_id")
            continue
        try:
            publish_yt.publish_now(channel, video_id, slot.isoformat())
            db.set_privacy(sid, "public")
            promoted += 1
            print(f"promoted {channel} story {sid} -> {slot.isoformat()}")
        except Exception as e:
            print(f"promote failed {channel} story {sid}: {e}")
    print(f"promoted {promoted}/{len(backlog)}")


def _vid(sid):
    row = db.DB.execute("SELECT yt_video_id FROM stories WHERE id=?", (sid,)).fetchone()
    return row[0] if row else None


if __name__ == "__main__":
    replay_all()
