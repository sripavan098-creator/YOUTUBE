import datetime
import json
import pathlib
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = pathlib.Path(__file__).resolve().parent.parent
IST = ZoneInfo("Asia/Kolkata")


def _service(channel):
    tok = json.loads((ROOT / "tokens" / f"yt_{channel}.json").read_text(encoding="utf-8"))
    creds = Credentials(
        None, refresh_token=tok["refresh_token"], client_id=tok["client_id"],
        client_secret=tok["client_secret"], token_uri="https://oauth2.googleapis.com/token",
        scopes=tok.get("scopes"))
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _slot(lcfg, step_min, index):
    """Pick the posting slot for this video.

    Research: 8:30 AM IST (commute) + 7:30 PM IST (prime time) are the two
    daily slots. index 0 → yt_start (morning), index 1 → yt_start_2 (evening),
    index 2+ → yt_start the next day with step_min offset.
    """
    now = datetime.datetime.now(IST)
    # Choose which start time based on even/odd index
    if index % 2 == 1 and lcfg.get("yt_start_2"):
        h, m = map(int, lcfg["yt_start_2"].split(":"))
        days_ahead = index // 2
    else:
        h, m = map(int, lcfg["yt_start"].split(":"))
        days_ahead = index // 2
    slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
    slot += datetime.timedelta(days=days_ahead, minutes=step_min * (index // 2))
    while slot < now + datetime.timedelta(minutes=20):
        slot += datetime.timedelta(days=1)
    return slot


def upload(channel, lcfg, step_min, index, script, video, source_url, public_ok=False):
    """Upload one Short.

    While the Cloud project is unaudited, `public_ok` stays False: the video is
    created private with no publishAt, because the API cannot publish it. Once the
    audit passes, pass True and the same call schedules it for its slot.
    """
    yt = _service(channel)
    slot = _slot(lcfg, step_min, index)

    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    if public_ok:
        status["publishAt"] = slot.astimezone(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

    desc = script.get("description") or script["script"].split(".")[0].strip()
    tags = script.get("tags") or [h.lstrip("#") for h in script["hashtags"]][:15]
    # first three hashtags are shown above the title, so lead with the strongest ones
    kw = ", ".join(script.get("search_terms", [])[:6])
    # Use title_with_hashtags if available (2-3 niche hashtags appended inside the title)
    # Research: hashtags IN the title are clickable and boost discovery
    upload_title = script.get("title_with_hashtags") or script["title"]
    body = {
        "snippet": {
            "title": upload_title[:100],
            "description": f"{desc}\n\n" + (f"{kw}\n\n" if kw else "") +
                           f"Source: {source_url}\n\n{' '.join(script['hashtags'])}",
            "tags": tags,
            "categoryId": "28",
            "defaultLanguage": lcfg["lang"],
            "defaultAudioLanguage": lcfg["lang"],
        },
        "status": status,
    }

    media = MediaFileUpload(video, chunksize=-1, resumable=True, mimetype="video/mp4")
    resp = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return resp["id"], slot.isoformat(), status["privacyStatus"]


def publish_now(channel, video_id, slot=None):
    """Flip an already-uploaded private video to public (or schedule it).

    Uses videos.update, which needs the `youtube` or `youtube.force-ssl` scope.
    """
    yt = _service(channel)
    status = {"privacyStatus": "public"}
    if slot:
        status["privacyStatus"] = "private"
        status["publishAt"] = slot
    yt.videos().update(part="status", body={"id": video_id, "status": status}).execute()
    return status
