"""Convert still photos into moving portrait shots and optionally enhance audio."""
import os
import pathlib
import shutil
import subprocess


FPS = 30


def still_to_clip(src, dst, seconds, aggressive=False, reverse=False):
    seconds = max(0.6, float(seconds))
    rate = 0.0035 if aggressive else 0.0012
    if reverse:
        zoom = f"max(1.18-{rate}*on,1.0)"
    else:
        zoom = f"min(1.0+{rate}*on,1.18)"
    vf = (
        "scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
        f"zoompan=z='{zoom}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s=1080x1920:fps={FPS}"
    )
    try:
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(src),
                "-vf", vf, "-t", f"{seconds + 0.15:.2f}", "-an",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-pix_fmt", "yuv420p", str(dst),
            ],
            check=True,
        )
        return dst
    except Exception as error:
        print(f"  motion failed ({str(error)[:60]}), using still", flush=True)
        alternate = pathlib.Path(dst).with_suffix(".jpg")
        shutil.copy(src, alternate)
        return alternate


def enhance_audio(voice, beats, out_mp3, music_dir="assets/music"):
    """Optional whoosh, bed, and loudness pass; never changes beat timings."""
    if os.getenv("AUDIO_ENHANCE", "0") != "1" or not shutil.which("ffmpeg"):
        return voice
    tracks = []
    music_path = pathlib.Path(music_dir)
    if music_path.exists():
        tracks = [
            path for path in music_path.glob("*")
            if path.suffix.lower() in (".mp3", ".m4a", ".wav")
        ]

    inputs = ["-i", str(voice)]
    filters = ["[0:a]volume=1.0[v]"]
    labels = ["[v]"]
    next_input = 1
    if tracks:
        inputs += ["-stream_loop", "-1", "-i", str(tracks[0])]
        filters.append(f"[{next_input}:a]volume=0.10,afade=t=in:d=1[m]")
        labels.append("[m]")
        next_input += 1

    whoosh_times = [float(cut) for cut in (beats or [])][1:]
    for ms_index, cut in enumerate(whoosh_times):
        milliseconds = int(cut * 1000)
        inputs += [
            "-f", "lavfi", "-i", "anoisesrc=d=0.22:c=pink:a=0.22",
        ]
        filters.append(
            f"[{next_input}:a]afade=t=in:d=0.06,afade=t=out:st=0.10:d=0.12,"
            f"adelay={milliseconds}|{milliseconds}[w{ms_index}]"
        )
        labels.append(f"[w{ms_index}]")
        next_input += 1

    filter_complex = (
        ";".join(filters)
        + ";"
        + "".join(labels)
        + f"amix=inputs={len(labels)}:duration=first:dropout_transition=0,"
        + "loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
    )
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y"] + inputs
            + ["-filter_complex", filter_complex, "-map", "[aout]",
               "-codec:a", "libmp3lame", "-qscale:a", "2", str(out_mp3)],
            check=True,
        )
        print("  audio enhanced (cuts + bed + -14 LUFS)", flush=True)
        return out_mp3
    except Exception as error:
        print(f"  audio enhance skipped ({str(error)[:60]})", flush=True)
        return voice
