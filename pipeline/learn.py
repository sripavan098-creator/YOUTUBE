"""Learning loop: let real results steer what gets made next.

Every night, public statistics for the videos we uploaded are pulled through the YouTube
API (views, likes, comments) and stored per hook archetype and layout. When the next script
is written, the hook archetype is chosen with an epsilon-greedy bandit: mostly the one with
the best average views for that channel, sometimes the least-tried, so it keeps exploring.

Honest limit: while uploads are private (yt_public_after_audit: false) YouTube reports no
views, so the loop only starts steering once videos are public. Until then it simply
rotates through the archetypes evenly, which is the right thing to do with no data.
"""
import random

from pipeline import db
from pipeline.scripts import HOOK_ARCHETYPES

EPSILON = 0.3
MIN_VIEWS_SIGNAL = 50  # below this total, the data is noise and we just rotate


def refresh_stats():
    """Pull statistics for every uploaded video older than a day. Never raises."""
    from pipeline import publish_yt
    rows = db.uploaded_stories()
    by_channel = {}
    for sid, ch, vid, arche, layout in rows:
        by_channel.setdefault(ch, []).append((sid, vid, arche, layout))
    done = 0
    for ch, items in by_channel.items():
        try:
            yt = publish_yt._service(ch)
        except Exception as e:
            print(f"learn: no credentials for {ch}: {str(e)[:80]}")
            continue
        for i in range(0, len(items), 50):
            chunk = items[i:i + 50]
            try:
                resp = yt.videos().list(part="statistics",
                                        id=",".join(v for _, v, _, _ in chunk)).execute()
            except Exception as e:
                print(f"learn: stats call failed for {ch}: {str(e)[:80]}")
                continue
            stats = {it["id"]: it.get("statistics", {}) for it in resp.get("items", [])}
            for sid, vid, arche, layout in chunk:
                st = stats.get(vid)
                if st is None:
                    continue
                db.save_perf(sid, ch, arche, layout, int(st.get("viewCount", 0)),
                             int(st.get("likeCount", 0)), int(st.get("commentCount", 0)))
                done += 1
    print(f"learn: updated stats for {done} videos")
    return done


def pick_archetype(channel, recent=()):
    """Choose the hook archetype for the next script on this channel."""
    names = list(HOOK_ARCHETYPES)
    rows = db.perf_rows(channel)
    stats = {}
    for arche, _layout, views in rows:
        if arche in HOOK_ARCHETYPES:
            stats.setdefault(arche, []).append(views)
    tried = {a: len(v) for a, v in stats.items()}
    total_views = sum(sum(v) for v in stats.values())
    fresh = [n for n in names if n not in list(recent)[-2:]] or names
    # never tried -> try it before exploiting anything
    untried = [n for n in fresh if n not in tried]
    if untried and (total_views < MIN_VIEWS_SIGNAL or random.random() < 0.7):
        return random.choice(untried)
    if total_views < MIN_VIEWS_SIGNAL:
        return min(fresh, key=lambda n: tried.get(n, 0))
    if random.random() < EPSILON:
        return min(fresh, key=lambda n: tried.get(n, 0))
    return max((n for n in fresh if n in stats), key=lambda n: sum(stats[n]) / len(stats[n]),
               default=random.choice(fresh))
