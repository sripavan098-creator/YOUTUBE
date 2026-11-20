import { useMemo } from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import type { Word } from './ShortProps';

const MAX_WORDS = 3;
const GAP_BREAK = 0.35; // a pause this long always starts a new caption
const SENTENCE_END = /[.!?।…]$/;

export const clean = (s: string) => s.replace(/[.,!?।…"'“”‘’():;-]/g, '').trim();

// Short phrases, never a full sentence, and never a phrase that straddles a sentence end:
// the viewer reads exactly what is being said at the moment it is said.
export const buildChunks = (words: Word[]): Word[][] => {
  const out: Word[][] = [];
  let cur: Word[] = [];
  words.forEach((w, i) => {
    const prev = cur[cur.length - 1];
    if (cur.length && prev && w.start - prev.end > GAP_BREAK) {
      out.push(cur);
      cur = [];
    }
    cur.push(w);
    if (cur.length >= MAX_WORDS || SENTENCE_END.test(w.text.trim()) || i === words.length - 1) {
      out.push(cur);
      cur = [];
    }
  });
  if (cur.length) out.push(cur);
  return out;
};

export const useActiveChunk = (chunks: Word[][]): Word[] | null => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  return useMemo(() => {
    for (let i = chunks.length - 1; i >= 0; i--) {
      const c = chunks[i];
      if (t >= c[0].start - 0.04) {
        return t <= c[c.length - 1].end + 0.25 ? c : null;
      }
    }
    return null;
  }, [chunks, t]);
};

export const useNow = (): number => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return frame / fps;
};
