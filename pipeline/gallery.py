import html
import pathlib
import sqlite3
import subprocess


ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
THUMBS = OUT / "_thumbnails"


def make_thumbnail(video: pathlib.Path) -> pathlib.Path:
    THUMBS.mkdir(parents=True, exist_ok=True)
    thumb = THUMBS / f"{video.stem}.jpg"
    if thumb.exists():
        return thumb
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            "1",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=270:-1",
            str(thumb),
        ],
        check=False,
    )
    return thumb if thumb.exists() else pathlib.Path()


def build() -> pathlib.Path:
    db = sqlite3.connect(ROOT / "engine.db")
    rows = db.execute(
        "SELECT id, channel, day, title, layout, video_path, status "
        "FROM stories ORDER BY day DESC, id DESC"
    ).fetchall()

    cards = []
    for sid, channel, day, title, layout, video_path, status in rows:
        if status != "done" or not video_path:
            continue
        video = pathlib.Path(video_path)
        if not video.exists():
            continue
        thumb = make_thumbnail(video)
        thumb_src = thumb.relative_to(OUT).as_posix() if thumb else ""
        cards.append(
            f"""
            <article class="card">
              <a class="preview" href="{html.escape(video.name)}" target="_blank">
                {f'<img src="_thumbnails/{html.escape(thumb.name)}" alt="" loading="lazy">' if thumb_src else '<div class="placeholder">VIDEO</div>'}
              </a>
              <div class="meta">
                <div class="topline"><span class="channel {html.escape(channel)}">{html.escape(channel.upper())}</span><span>{html.escape(day or "")}</span></div>
                <h2>{html.escape(title or f"Video {sid}")}</h2>
                <div class="bottomline"><span>{html.escape(layout or "render")}</span><a href="{html.escape(video.name)}" download>Download</a></div>
              </div>
            </article>
            """
        )

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Video Gallery</title>
  <style>
    *{{box-sizing:border-box}} body{{margin:0;background:#08111f;color:#edf3ff;font-family:Inter,system-ui,sans-serif}}
    header{{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;align-items:center;padding:18px 24px;background:rgba(8,17,31,.92);border-bottom:1px solid #1d2d45;backdrop-filter:blur(12px)}}
    h1{{font-size:20px;margin:0}} .count{{color:#91a4bd;font-size:14px}}
    main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:18px;padding:24px}}
    .card{{overflow:hidden;border:1px solid #1d2d45;border-radius:16px;background:#101c2d;box-shadow:0 12px 30px rgba(0,0,0,.18)}}
    .preview{{display:flex;align-items:center;justify-content:center;height:340px;background:#050a12;overflow:hidden}}
    .preview img{{width:100%;height:100%;object-fit:cover;transition:transform .25s}} .preview:hover img{{transform:scale(1.03)}}
    .placeholder{{color:#5e7188;font-weight:800;letter-spacing:.18em}}
    .meta{{padding:14px}} .topline,.bottomline{{display:flex;align-items:center;justify-content:space-between;color:#91a4bd;font-size:12px}}
    .channel{{padding:5px 8px;border-radius:999px;font-weight:800}} .channel.hi{{background:#ff8a241f;color:#ffad62}} .channel.te{{background:#06b6d41f;color:#67dbe9}}
    h2{{min-height:58px;margin:12px 0;font-size:15px;line-height:1.35}} .bottomline{{border-top:1px solid #1d2d45;padding-top:11px}} a{{color:#9dd9ff;text-decoration:none}}
  </style>
</head>
<body>
  <header><h1>Rendered videos</h1><div class="count">{len(cards)} videos</div></header>
  <main>{''.join(cards)}</main>
</body>
</html>
"""
    index = OUT / "index.html"
    index.write_text(page, encoding="utf-8")
    return index


if __name__ == "__main__":
    print(build())
