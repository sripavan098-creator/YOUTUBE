import { useMemo } from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import type { Word } from './ShortProps';

// Show a short phrase at a time rather than one word: single-word captions read as
// stutter and make the timing look wrong even when it is accurate.
const WORDS_PER_CHUNK = 3;

export const useActiveChunk = (words: Word[]): Word[] | null => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const chunks = useMemo(() => {
    const out: Word[][] = [];
    for (let i = 0; i < words.length; i += WORDS_PER_CHUNK) {
      out.push(words.slice(i, i + WORDS_PER_CHUNK));
    }
    return out;
  }, [words]);

  return useMemo(() => {
    const hit = chunks.find(
      (c) => c.length > 0 && t >= c[0].start - 0.05 && t <= c[c.length - 1].end + 0.3
    );
    return hit ?? null;
  }, [chunks, t]);
};

export const useNow = (): number => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return frame / fps;
};
