import os
import re
import time

import requests


def _api():
    return f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN']}"


def _drain():
    """Consume updates that arrived before this run, so an old 'ok' cannot approve today."""
    offset = None
    try:
        for _ in range(5):
            res = requests.get(f"{_api()}/getUpdates",
                               params={"timeout": 0, "offset": offset}, timeout=20).json()
            batch = res.get("result", [])
            if not batch:
                break
            offset = batch[-1]["update_id"] + 1
    except Exception as e:
        print(f"telegram drain skipped: {e}")
    return offset


def review(story_angles_pairs, timeout_s=5):
    """Return [(story, angle), ...] for the stories/angles the editor picked.

    Reply grammar: '1A,2C,3B' picks an angle per story; 'skip 4' drops story 4;
    'auto' takes angle A for everything. No reply inside the timeout = angle A.
    """
    if not story_angles_pairs:
        return []
    if not os.environ.get("TG_BOT_TOKEN") or not os.environ.get("TG_CHAT_ID"):
        print("WARNING: Telegram not configured — defaulting every story to angle A")
        return [(st, angles[0]) for st, angles in story_angles_pairs]

    chat = os.environ["TG_CHAT_ID"]
    offset = _drain()
    started = time.time()

    lines = [f"Today's stories — reply '1A,2C,3B' or 'skip 4'. "
             f"No reply in {timeout_s // 60} min = angle A for all."]
    for i, (story, angles) in enumerate(story_angles_pairs):
        lines.append(f"\n{i + 1}. {story['title']}")
        for j, angle in enumerate(angles):
            lines.append(f"   {i + 1}{chr(65 + j)}: {angle['take']}")
    requests.post(f"{_api()}/sendMessage", data={"chat_id": chat, "text": "\n".join(lines)},
                  timeout=30)

    deadline = started + timeout_s
    picks = {}
    while time.time() < deadline:
        try:
            res = requests.get(f"{_api()}/getUpdates",
                               params={"timeout": 25, "offset": offset}, timeout=40).json()
        except Exception as e:
            print(f"telegram poll error: {e}")
            time.sleep(5)
            continue

        for update in res.get("result", []):
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id")) != str(chat):
                continue
            if msg.get("date", 0) < started:
                continue
            text = (msg.get("text") or "").lower().strip()

            if text == "auto":
                return [(st, angles[0]) for st, angles in story_angles_pairs]
            if text.startswith("skip"):
                for token in text.replace("skip", "").replace(",", " ").split():
                    if token.isdigit():
                        picks[int(token) - 1] = None
            for m in re.finditer(r"(\d+)([a-c])", text):
                picks[int(m.group(1)) - 1] = m.group(2).upper()
            if len(picks) >= len(story_angles_pairs):
                break

    out = []
    for i, (story, angles) in enumerate(story_angles_pairs):
        if picks.get(i, "A") is None:
            continue
        idx = ord(picks.get(i, "A")) - 65
        out.append((story, angles[idx] if idx < len(angles) else angles[0]))
    return out
