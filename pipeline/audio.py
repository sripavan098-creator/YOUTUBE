"""Audio finishing: loudness, voice presence, scene-cut whooshes and ducked music.

The voice stays the master clock. Nothing here changes the audio length, so the word
timings written by voice.synth remain valid for the captions.
"""
import glob
import pathlib
import random
import subprocess

from mutagen.mp3 import MP3

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
TARGET_LUFS = -14  # what Shorts and Reels normalise toward; louder than that gets turned down


def _ffmpeg(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, check=True)


def _whoosh():
    """A soft transition sweep, synthesised once so no sample licence is involved.
    Drop your own file at assets/sfx/whoosh.wav to override."""
    custom = ASSETS / "sfx" / "whoosh.wav"
    if custom.exists():
        return custom
    out = ASSETS / "sfx" / "_whoosh_generated.wav"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg(["-f", "lavfi", "-i", "anoisesrc=d=0.45:c=pink:a=0.6",
                 "-af", "highpass=f=500,lowpass=f=6000,afade=t=in:d=0.18,"
                        "afade=t=out:st=0.2:d=0.25,volume=0.9", "-ar", "48000", str(out)])
    return out


def _music():
    files = [f for ext in ("mp3", "wav", "m4a") for f in glob.glob(str(ASSETS / "music" / f"*.{ext}"))]
    return random.choice(files) if files else None


def finish(mp3_in, mp3_out, cut_times, duration, sfx=True, music_volume=0.12):
    """Write the finished mix to mp3_out and return its length in seconds."""
    cuts = [t for t in cut_times if t > 0.4]
    inputs = ["-i", str(mp3_in)]
    chains = ["[0:a]highpass=f=70,acompressor=threshold=0.1:ratio=3:attack=5:release=80,"
              "aresample=48000,aformat=channel_layouts=stereo[v]"]
    mix = []

    music = _music()
    if music:
        inputs += ["-stream_loop", "-1", "-i", music]
        mi = len(inputs) // 2 - 1
        chains.append("[v]asplit=2[vmix][vsc]")
        chains.append(f"[{mi}:a]aresample=48000,aformat=channel_layouts=stereo,"
                      f"volume={music_volume},atrim=0:{duration + 0.5:.2f}[m]")
        # duck the music under speech so it never fights the voice
        chains.append("[m][vsc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md]")
        mix = ["[vmix]", "[md]"]
    else:
        mix = ["[v]"]

    if sfx and cuts:
        inputs += ["-i", str(_whoosh())]
        wi = len(inputs) // 2 - 1
        k = len(cuts)
        labels = "".join(f"[w{i}]" for i in range(k))
        chains.append(f"[{wi}:a]aformat=channel_layouts=stereo,asplit={k}{labels}"
                      if k > 1 else f"[{wi}:a]aformat=channel_layouts=stereo[w0]")
        for i, t in enumerate(cuts):
            ms = max(0, int((t - 0.12) * 1000))
            chains.append(f"[w{i}]adelay={ms}|{ms},volume=0.35[s{i}]")
            mix.append(f"[s{i}]")

    chains.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,"
                  f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=9[out]")
    _ffmpeg(inputs + ["-filter_complex", ";".join(chains), "-map", "[out]",
                      "-c:a", "libmp3lame", "-q:a", "2", str(mp3_out)])
    return MP3(str(mp3_out)).info.length
