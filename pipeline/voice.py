import asyncio
import json
import time

import edge_tts
from mutagen.mp3 import MP3


async def _run(text, voice, rate, pitch, volume, mp3_path, words_path):
    words = []
    with open(mp3_path, "wb") as f:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch,
                                           volume=volume, boundary="WordBoundary")
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / 1e7,
                    "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                })
    if not words:
        raise RuntimeError("edge-tts returned no word boundaries")
    with open(words_path, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False)


def synth(text, voice, rate, mp3_path, words_path, attempts=3, pitch="+0Hz", volume="+0%"):
    """pitch/volume are optional per-channel tuning (config.yaml: pitch, volume).
    A small positive pitch and a slightly faster rate reads as more energetic."""
    last = None
    for i in range(attempts):
        try:
            asyncio.run(_run(text, voice, rate, pitch, volume, mp3_path, words_path))
            return MP3(mp3_path).info.length
        except Exception as e:
            last = e
            print(f"tts attempt {i + 1} failed: {e}")
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"tts failed for {voice}: {last}")
