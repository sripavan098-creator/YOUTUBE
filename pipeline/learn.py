"""Learning loop: let real results steer what gets made next.

Every night, public statistics for the videos we uploaded are pulled through the YouTube
Data and Analytics APIs and stored per hook archetype and layout. The chooser uses retention
and subscriber conversion when available, falling back to views for older records or when
Analytics access has not been granted.

Honest limit: while uploads are private (yt_public_after_audit: false) YouTube reports no
views, so the loop only starts steering once videos are public. Until then it explores
archetypes rather than treating missing data as a success or failure signal.
"""
import datetime
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
    for sid, ch, vid, arche, layout, day in rows:
        by_channel.setdefault(ch, []).append((sid, vid, arche, layout, day))
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
                                        id=",".join(v for _, v, _, _, _ in chunk)).execute()
            except Exception as e:
                print(f"learn: stats call failed for {ch}: {str(e)[:80]}")
                continue
            stats = {it["id"]: it.get("statistics", {}) for it in resp.get("items", [])}

            analytics_stats = {}
            try:
                analytics = publish_yt._analytics_service(ch)
                end_date = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
                start_date = min(item[4] for item in chunk)
                report = analytics.reports().query(
                    ids="channel==MINE",
                    startDate=start_date,
                    endDate=end_date,
                    metrics=("engagedViews,averageViewPercentage,averageViewDuration,"
                             "subscribersGained"),
                    dimensions="video",
                    filters="video==" + ",".join(v for _, v, _, _, _ in chunk),
                ).execute()
                for values in report.get("rows", []):
                    analytics_stats[values[0]] = {
                        "engaged_views": int(values[1]),
                        "average_view_percentage": float(values[2]),
                        "average_view_duration": float(values[3]),
                        "subscribers_gained": int(values[4]),
                    }
            except Exception as e:
                print(f"learn: retention analytics unavailable for {ch}: {str(e)[:100]}")

            for sid, vid, arche, layout, _day in chunk:
                st = stats.get(vid)
                if st is None:
                    continue
                retention = analytics_stats.get(vid, {})
                db.save_perf(sid, ch, arche, layout, int(st.get("viewCount", 0)),
                             int(st.get("likeCount", 0)), int(st.get("commentCount", 0)),
                             **retention)
                done += 1
    print(f"learn: updated stats for {done} videos")
    return done


def pick_archetype(channel, recent=()):
    """Choose the hook archetype for the next script on this channel."""
    names = list(HOOK_ARCHETYPES)
    rows = db.perf_rows(channel)
    has_retention = any(row[6] is not None for row in rows)
    stats = {}
    total_signal = 0
    for row in rows:
        arche, _layout, views, _likes, _comments, engaged, avg_pct, _avg_duration, subs = row
        if arche in HOOK_ARCHETYPES:
            if has_retention:
                if avg_pct is None:
                    continue
                signal = max(engaged or views, 1)
                subscribers_per_thousand = max(0, subs or 0) * 1000 / signal
                score = float(avg_pct) + min(5.0, subscribers_per_thousand * 0.1)
                total_signal += signal
            else:
                score = float(views)
                total_signal += views
            stats.setdefault(arche, []).append(score)
    tried = {a: len(v) for a, v in stats.items()}
    total_views = total_signal
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
