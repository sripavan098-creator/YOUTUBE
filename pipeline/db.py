import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = sqlite3.connect(ROOT / "engine.db", check_same_thread=False)

# `stories` is keyed per channel: the same source URL may be covered by both
# channels under different angles, so uniqueness is (channel, url), not url alone.
DB.executescript("""
CREATE TABLE IF NOT EXISTS stories(
    id INTEGER PRIMARY KEY,
    channel TEXT NOT NULL,
    day TEXT, url TEXT, title TEXT, body TEXT,
    layout TEXT, angle_id TEXT, video_path TEXT,
    yt_video_id TEXT, privacy TEXT DEFAULT 'private',
    status TEXT DEFAULT 'new',
    UNIQUE(channel, url));
CREATE TABLE IF NOT EXISTS igq(
    id INTEGER PRIMARY KEY,
    story_id INT, channel TEXT, path TEXT, caption TEXT,
    publish_at TEXT, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS longform(
    id INTEGER PRIMARY KEY,
    channel TEXT NOT NULL, day TEXT, yt_video_id TEXT, video_path TEXT,
    UNIQUE(channel, day));
""")


def seen(channel, url):
    """Skip a story only if this channel already produced it; 'failed' rows retry."""
    row = DB.execute("SELECT status FROM stories WHERE channel=? AND url=?",
                     (channel, url)).fetchone()
    return row is not None and row[0] != "failed"


def add_story(day, channel, url, title, body):
    DB.execute("INSERT OR IGNORE INTO stories(day,channel,url,title,body) VALUES(?,?,?,?,?)",
               (day, channel, url, title, body))
    DB.commit()
    return DB.execute("SELECT id FROM stories WHERE channel=? AND url=?",
                      (channel, url)).fetchone()[0]


def set_status(sid, st):
    DB.execute("UPDATE stories SET status=? WHERE id=?", (st, sid))
    DB.commit()


def set_produced(sid, layout, angle_id, video_path, yt_video_id, privacy):
    DB.execute("UPDATE stories SET layout=?, angle_id=?, video_path=?, yt_video_id=?, privacy=? "
               "WHERE id=?", (layout, angle_id, video_path, yt_video_id, privacy, sid))
    DB.commit()


def recent_layouts(channel, n=3):
    rows = DB.execute(
        "SELECT layout FROM stories WHERE channel=? AND layout IS NOT NULL "
        "ORDER BY id DESC LIMIT ?", (channel, n)).fetchall()
    return [r[0] for r in rows]


def week_stories(since, channel):
    return DB.execute(
        "SELECT id,day,title FROM stories WHERE channel=? AND day>=? AND status='done' "
        "ORDER BY day DESC", (channel, since)).fetchall()


def private_backlog():
    return DB.execute(
        "SELECT id,channel,url,title,video_path FROM stories "
        "WHERE yt_video_id IS NOT NULL AND privacy='private'").fetchall()


def queue_ig(sid, channel, path, cap, at):
    DB.execute("INSERT INTO igq(story_id,channel,path,caption,publish_at) VALUES(?,?,?,?,?)",
               (sid, channel, path, cap, at))
    DB.commit()


def due_ig(now_iso):
    return DB.execute(
        "SELECT id,story_id,channel,path,caption FROM igq "
        "WHERE status='pending' AND publish_at<=?", (now_iso,)).fetchall()


def mark_ig(row_id, st):
    DB.execute("UPDATE igq SET status=? WHERE id=?", (st, row_id))
    DB.commit()


def add_longform(channel, day, yt_video_id, video_path):
    DB.execute("INSERT OR REPLACE INTO longform(channel,day,yt_video_id,video_path) "
               "VALUES(?,?,?,?)", (channel, day, yt_video_id, video_path))
    DB.commit()


def count_longform(channel, since):
    return DB.execute("SELECT COUNT(*) FROM longform WHERE channel=? AND day>=?",
                      (channel, since)).fetchone()[0]


def built_longform_today(channel, day):
    """Guards against a daemon restart uploading a second long-form the same day."""
    return DB.execute("SELECT 1 FROM longform WHERE channel=? AND day=?",
                      (channel, day)).fetchone() is not None


def set_privacy(sid, privacy):
    DB.execute("UPDATE stories SET privacy=? WHERE id=?", (privacy, sid))
    DB.commit()
