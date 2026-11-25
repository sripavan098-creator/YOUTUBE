"""Idempotency guards: one queue row and one upload per story and channel."""
import datetime
import pathlib
import re


def _publish_key(name, path):
    filename = str(name or pathlib.Path(str(path)).name)
    if re.fullmatch(r"\d+_[a-z0-9_-]+\.mp4", filename, re.IGNORECASE):
        return filename
    return filename + "|" + str(pathlib.Path(str(path)).resolve())


def _tables(db_mod):
    con = db_mod.DB
    con.execute(
        "CREATE TABLE IF NOT EXISTS ig_queued_once "
        "(sid INTEGER, channel TEXT, PRIMARY KEY (sid, channel))"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS ig_posted_once "
        "(key TEXT, channel TEXT, at TEXT, PRIMARY KEY (key, channel))"
    )
    con.execute(
        "INSERT OR IGNORE INTO ig_queued_once (sid, channel) "
        "SELECT DISTINCT story_id, channel FROM igq "
        "WHERE story_id IS NOT NULL AND channel IS NOT NULL"
    )
    con.commit()


def install(db_mod, publish_mod):
    _tables(db_mod)
    con = db_mod.DB

    if not getattr(db_mod, "_ig_once_q", False):
        db_mod._ig_once_q = True
        original_queue = db_mod.queue_ig

        def queue_ig(sid, channel, path, cap, at):
            cursor = con.execute(
                "INSERT OR IGNORE INTO ig_queued_once (sid, channel) VALUES (?, ?)",
                (int(sid), str(channel)),
            )
            con.commit()
            if cursor.rowcount == 0:
                return None
            try:
                return original_queue(sid, channel, path, cap, at)
            except Exception:
                con.execute(
                    "DELETE FROM ig_queued_once WHERE sid=? AND channel=?",
                    (int(sid), str(channel)),
                )
                con.commit()
                raise

        db_mod.queue_ig = queue_ig

    if not getattr(publish_mod, "_ig_once_p", False):
        publish_mod._ig_once_p = True
        original_publish = publish_mod.publish

        def publish(lang, path, caption, name=None, *args, **kwargs):
            key = _publish_key(name, path)
            channel = str(lang)
            cursor = con.execute(
                "INSERT OR IGNORE INTO ig_posted_once (key, channel, at) "
                "VALUES (?, ?, ?)",
                (
                    key,
                    channel,
                    datetime.datetime.now().isoformat(timespec="seconds"),
                ),
            )
            con.commit()
            if cursor.rowcount == 0:
                print("IG skip (already posted once): " + key, flush=True)
                return None
            try:
                return original_publish(lang, path, caption, name, *args, **kwargs)
            except Exception:
                con.execute(
                    "DELETE FROM ig_posted_once WHERE key=? AND channel=?",
                    (key, channel),
                )
                con.commit()
                raise

        publish_mod.publish = publish

    print("[ig_once] queue + upload idempotency active", flush=True)


def already_posted(db_mod, sid, channel):
    _tables(db_mod)
    key = str(sid) + "_" + str(channel) + ".mp4"
    row = db_mod.DB.execute(
        "SELECT 1 FROM ig_posted_once WHERE key=? AND channel=?",
        (key, str(channel)),
    ).fetchone()
    return row is not None
