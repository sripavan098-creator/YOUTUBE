"""Turn the written beats into cut times using the TTS word timings."""


def beat_times(lines, words, duration):
    """Return [(start, end), ...] seconds, one per line.

    Uses exact word boundaries when the TTS token count matches the script's; otherwise
    falls back to a character-proportional split of the audio, which is still close
    enough to land cuts on sentence starts.
    """
    counts = [max(1, len(l.split())) for l in lines]
    total = sum(counts)
    starts = [0.0]
    if words and len(words) == total:
        idx = 0
        for c in counts[:-1]:
            idx += c
            starts.append(float(words[idx]["start"]))
    elif words:
        chars = [max(1, len(l)) for l in lines]
        cum, tot = 0, sum(chars)
        for c in chars[:-1]:
            cum += c
            i = min(len(words) - 1, round(cum / tot * len(words)))
            starts.append(float(words[i]["start"]))
    else:
        step = duration / len(lines)
        starts = [i * step for i in range(len(lines))]
    # strictly increasing, and never past the audio
    for i in range(1, len(starts)):
        starts[i] = max(starts[i], starts[i - 1] + 0.4)
    starts = [min(s, max(0.0, duration - 0.3)) for s in starts]
    ends = starts[1:] + [duration]
    return list(zip(starts, ends))
