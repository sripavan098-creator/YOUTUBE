"""Post pending IG queue entries once, with a configurable delay between posts.

    python -m pipeline.ig_drain --dry-run
    python -m pipeline.ig_drain
    python -m pipeline.ig_drain --gap 600 --channel te
"""
import argparse
import datetime
import pathlib
import time

from pipeline import db, ig_once, publish_ig


FAR = "2099-01-01T00:00:00"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gap", type=int, default=600,
        help="seconds between posts (default: 600)",
    )
    parser.add_argument("--channel", default="", help="restrict to one channel, e.g. te")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.gap < 0:
        parser.error("--gap must be non-negative")

    ig_once.install(db, publish_ig)

    rows = sorted(db.due_ig(FAR), key=lambda row: row[0])
    print("pending queue rows found: " + str(len(rows)))

    keep, seen, duplicates, posted = [], set(), [], []
    for row in rows:
        row_id, sid, channel = row[0], row[1], row[2]
        if args.channel and channel != args.channel:
            continue
        key = (sid, channel)
        if key in seen:
            duplicates.append(row_id)
            continue
        if ig_once.already_posted(db, sid, channel):
            posted.append(row_id)
            seen.add(key)
            continue
        seen.add(key)
        keep.append(row)

    if not args.dry_run:
        for row_id in duplicates:
            db.mark_ig(row_id, "duplicate")
        for row_id in posted:
            db.mark_ig(row_id, "done")
    if duplicates or posted:
        action = "would remove" if args.dry_run else "removed"
        print(
            action + " " + str(len(duplicates)) + " duplicate rows, "
            + str(len(posted)) + " already-posted rows"
        )

    todo = []
    for row_id, sid, channel, path, caption in keep:
        video_path = pathlib.Path(path)
        if not video_path.is_absolute():
            video_path = db.ROOT / video_path
        if not video_path.exists():
            action = "would mark failed" if args.dry_run else "marking failed"
            print("MISSING file, " + action + ": " + str(video_path))
            if not args.dry_run:
                db.mark_ig(row_id, "failed")
            continue
        todo.append((row_id, sid, channel, str(video_path), caption))

    if args.limit:
        todo = todo[:args.limit]

    if not todo:
        print("nothing to post — queue is clean")
        return

    start = datetime.datetime.now()
    print("\nplan (" + str(len(todo)) + " videos, " + str(args.gap // 60) + " min apart):")
    for index, row in enumerate(todo):
        sid, channel, path = row[1], row[2], row[3]
        when = start + datetime.timedelta(seconds=args.gap * index)
        print(
            "  " + when.strftime("%H:%M") + "  story " + str(sid) + "  "
            + channel + "  " + pathlib.Path(path).name
        )
    last_post = start + datetime.timedelta(seconds=args.gap * (len(todo) - 1))
    print("finishes about " + last_post.strftime("%H:%M"))

    if args.dry_run:
        print("\n--dry-run: no queue rows changed and nothing posted")
        return

    print("\nstarting in 5s — Ctrl+C to abort")
    time.sleep(5)

    succeeded = failed = 0
    for index, (row_id, sid, channel, path, caption) in enumerate(todo):
        if index:
            next_time = datetime.datetime.now() + datetime.timedelta(seconds=args.gap)
            print(
                "waiting " + str(args.gap // 60) + " min -> next at "
                + next_time.strftime("%H:%M"),
                flush=True,
            )
            time.sleep(args.gap)
        print(
            "[" + str(index + 1) + "/" + str(len(todo)) + "] posting story "
            + str(sid) + " on " + channel,
            flush=True,
        )
        try:
            publish_ig.publish(channel, path, caption, str(sid) + "_" + channel + ".mp4")
            db.mark_ig(row_id, "done")
            succeeded += 1
            print("  posted", flush=True)
        except Exception as error:
            db.mark_ig(row_id, "failed")
            failed += 1
            print("  FAILED: " + str(error)[:200], flush=True)

    print(
        "\ndone: " + str(succeeded) + " posted, " + str(failed) + " failed, "
        + str(len(duplicates)) + " duplicates removed"
    )


if __name__ == "__main__":
    main()
