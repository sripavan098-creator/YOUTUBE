import json
import math
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from pipeline import motion

ROOT = pathlib.Path(__file__).resolve().parent.parent
REMOTION = ROOT / "remotion"

COMPOSITIONS = {
    "list": "ShortList",
    "explainer": "ShortExplainer",
    "versus": "ShortVersus",
    "timeline": "ShortTimeline",
}

FPS = 30
TAIL = 0.6          # must match calculateMetadata in remotion/src/Root.tsx
FALLBACK_CUT = 4.0  # seconds per scene when no beat timings are supplied (long-form)
RENDER_CHUNK_FRAMES = 30


def npx_bin():
    exe = shutil.which("npx.cmd") if sys.platform == "win32" else shutil.which("npx")
    return exe or ("npx.cmd" if sys.platform == "win32" else "npx")


def _scenes(shot_paths, beats, duration):
    """Pair every cut with a media file (None = poster). Beats come from voice.synth_beats;
    without them (long-form) cut on a fixed rhythm and cycle through the footage."""
    total = duration + TAIL
    had_beats = bool(beats)
    if not beats:
        n = max(1, int(total // FALLBACK_CUT))
        step = total / n
        beats = [(i * step, (i + 1) * step) for i in range(n)]
    real = [p for p in shot_paths if p]
    out = []
    for i, (s, e) in enumerate(beats):
        if had_beats and i < len(shot_paths):
            src = shot_paths[i]
        else:
            src = real[i % len(real)] if real else None
        out.append((src, s, e))
    out[-1] = (out[-1][0], out[-1][1], total)  # the last scene runs through the tail
    return out


def _slam_time(word, words, s, e):
    """When the slammed word is actually spoken inside its beat."""
    strip = ".,!?।…\"'“”‘’():;-"
    key = word.strip(strip)
    for w in words:
        if s - 0.05 <= w["start"] < e and w["text"].strip(strip) == key:
            return w["start"]
    return None


def _prep_clip(src, dst, seconds):
    """Normalise a clip to exactly one scene: portrait 1080x1920, 30fps, silent, looped or
    trimmed to length. Rendering identical, pre-cut clips keeps Remotion fast and means a
    short stock clip can never freeze on its last frame."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(src),
         "-t", f"{seconds + 0.15:.2f}", "-an",
         "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps={FPS}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
         str(dst)], check=True)


def _decodable_visual(src):
    path = pathlib.Path(src)
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
             "-frames:v", "1", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _frame_ranges(total_frames, chunk_frames=RENDER_CHUNK_FRAMES):
    return [
        (start, min(start + chunk_frames, total_frames) - 1)
        for start in range(0, total_frames, chunk_frames)
    ]


def _render_command(comp, output, props, frame_range=None):
    command = [
        npx_bin(), "remotion", "render", comp, str(output), f"--props={props}",
        "--codec=h264", "--crf=20", "--concurrency=1",
        "--offthreadvideo-cache-size-in-bytes=16777216", "--offthreadvideo-video-threads=1",
        "--overwrite", "--log=error",
    ]
    if frame_range:
        command.extend(["--frames", f"{frame_range[0]}-{frame_range[1]}"])
    return command


def _render_chunks(comp, output, props, audio, total_frames):
    with tempfile.TemporaryDirectory(prefix="render_chunks_") as tmp:
        temp = pathlib.Path(tmp)
        chunks = []
        for index, frame_range in enumerate(_frame_ranges(total_frames)):
            chunk = temp / f"chunk_{index:03d}.mp4"
            subprocess.run(
                _render_command(comp, chunk, props, frame_range),
                cwd=str(REMOTION), check=True,
            )
            if not chunk.exists() or chunk.stat().st_size == 0:
                raise RuntimeError(f"Remotion produced no frames for {frame_range}")
            video_only = temp / f"video_{index:03d}.mp4"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(chunk),
                 "-map", "0:v:0", "-c:v", "copy", "-an", str(video_only)],
                check=True,
            )
            chunks.append(video_only)

        concat_list = temp / "concat.txt"
        concat_list.write_text(
            "".join(f"file '{chunk.as_posix()}'\n" for chunk in chunks),
            encoding="utf-8",
        )
        stitched = temp / "stitched.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
             "-i", str(concat_list), "-c", "copy", str(stitched)],
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(stitched), "-i", str(audio),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-movflags", "+faststart", str(temp / "final.mp4")],
            check=True,
        )
        shutil.move(str(temp / "final.mp4"), str(output))


def render(sid, channel, lcfg, script, mp3, words_json, duration, shot_paths, layout,
           beats=None):
    pub = REMOTION / "public" / "a" / str(sid) / channel
    if pub.exists():
        shutil.rmtree(pub)
    pub.mkdir(parents=True, exist_ok=True)
    shutil.copy(mp3, pub / "v.mp3")

    words = json.loads(pathlib.Path(words_json).read_text(encoding="utf-8"))
    meta = script.get("beats") or []
    use_meta = bool(beats) and len(meta) == len(beats)
    scenes = []
    for i, (src, s, e) in enumerate(_scenes(shot_paths, beats, duration)):
        sc = {"start": round(s, 3), "end": round(e, 3)}
        if src and not _decodable_visual(src):
            print(f"  unusable visual for scene {i}; using poster", flush=True)
            src = None
        if not src:
            sc.update(
                src="",
                kind="poster",
                posterText=meta[i].get("line", "") if use_meta else script.get("title", ""),
                posterKeyword=meta[i].get("shot", "") if use_meta else "",
            )
        elif str(src).lower().endswith((".mp4", ".mov", ".webm")):
            name = f"s{i}.mp4"
            _prep_clip(src, pub / name, e - s)
            sc.update(src=f"a/{sid}/{channel}/{name}", kind="video")
        else:
            if os.getenv("MOTION_STILLS", "1") == "1":
                made = motion.still_to_clip(
                    src,
                    pub / f"s{i}.mp4",
                    e - s,
                    aggressive=(i == 0),
                    reverse=(i % 2 == 1),
                )
                name = pathlib.Path(made).name
                sc.update(
                    src=f"a/{sid}/{channel}/{name}",
                    kind="video" if name.endswith(".mp4") else "image",
                )
            else:
                name = f"s{i}.jpg"
                shutil.copy(src, pub / name)
                sc.update(src=f"a/{sid}/{channel}/{name}", kind="image")
        if use_meta:
            b = meta[i]
            sc["role"] = b.get("role") or ("hook" if i == 0 else "fact")
            sc["shake"] = sc["role"] in ("rehook", "payoff") or bool(b.get("shake"))
            if i and b.get("slam"):
                sc["slam"] = b["slam"]
                at = _slam_time(b["slam"], words, s, e)
                if at is not None:
                    sc["slamAt"] = round(at, 3)
            if i and b.get("stat"):
                sc["stat"] = str(b["stat"])
        scenes.append(sc)

    props = {
        "lang": lcfg["lang"],
        "brandName": lcfg["brand"],
        "color": lcfg["color"],
        "accent": lcfg["accent"],
        "headline": script["title"],
        "hook": script.get("hook_text") or script["title"],
        "emphasis": script.get("emphasis", []),
        "cta": script.get("cta_screen") or script.get("cta_text") or lcfg["cta"],
        "audio": f"a/{sid}/{channel}/v.mp3",
        "audioDuration": duration,
        "words": words,
        "nudge": lcfg.get("nudge", ""),
        "scenes": scenes,
        "shots": [s["src"] for s in scenes if s["src"]],
    }
    props["handle"] = lcfg.get("handle", "")
    props["mascot"] = {"size": 96, "opacity": 0.9, "show": True, "cap": True}
    props["endCard"] = True
    props_file = pub / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    out = ROOT / "out" / f"{sid}_{channel}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    comp = "GuluShort"
    total_frames = math.ceil((duration + TAIL) * FPS)
    if total_frames > RENDER_CHUNK_FRAMES:
        _render_chunks(comp, out, props_file, pub / "v.mp3", total_frames)
    else:
        subprocess.run(
            _render_command(comp, out, props_file),
            cwd=str(REMOTION), check=True,
        )
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"render produced no output for {sid}/{channel}")

    # ── Thumbnail: grab a visually-rich frame at ~0.5 s ──────────────────────
    # YouTube shows this as the default thumbnail if none is uploaded.
    # We always extract and pass it to the uploader so it looks intentional.
    thumb = ROOT / "out" / f"{sid}_{channel}_thumb.jpg"
    try:
        # Seek to 0.5 s (hook card is visible → strong first impression)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(out),
             "-frames:v", "1", "-q:v", "2",
             "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
                    "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black",
             str(thumb)],
            check=True, timeout=30,
        )
        print(f"  [thumb] generated {thumb.name}", flush=True)
    except Exception as e:
        print(f"  [thumb] WARNING: could not extract thumbnail: {e}", flush=True)
        thumb = None

    return str(out), str(thumb) if thumb and thumb.exists() else None
