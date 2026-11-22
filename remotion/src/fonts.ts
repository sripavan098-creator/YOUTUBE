import { useEffect, useState } from 'react';
import { continueRender, delayRender } from 'remotion';
// Bundled with the repo (npm i), so a render never depends on a font CDN being reachable.
import '@fontsource/noto-sans-telugu/telugu-800.css';
import '@fontsource/noto-sans-telugu/telugu-900.css';
import '@fontsource/noto-sans-telugu/latin-800.css';
import '@fontsource/noto-sans-telugu/latin-900.css';
import '@fontsource/noto-sans-devanagari/devanagari-800.css';
import '@fontsource/noto-sans-devanagari/devanagari-900.css';
import '@fontsource/noto-sans-devanagari/latin-800.css';
import '@fontsource/noto-sans-devanagari/latin-900.css';

const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

export const fontFor = (lang: 'hi' | 'te' | 'en'): string => {
  if (lang === 'hi') return `"Noto Sans Devanagari", ${SANS}`;
  if (lang === 'te') return `"Noto Sans Telugu", ${SANS}`;
  return SANS;
};

// Hold the render until the glyphs are actually loaded, so frame 1 is never in a fallback font.
export const useFontsReady = (lang: 'hi' | 'te' | 'en') => {
  const [handle] = useState(() => delayRender('fonts'));
  useEffect(() => {
    const fam = lang === 'hi' ? 'Noto Sans Devanagari' : lang === 'te' ? 'Noto Sans Telugu' : '';
    const sample = lang === 'hi' ? 'अआक' : lang === 'te' ? 'అఆక' : 'A';
    const loads = fam
      ? [`800 60px "${fam}"`, `900 60px "${fam}"`].map((f) => document.fonts.load(f, sample))
      : [];
    Promise.all(loads).catch(() => undefined).finally(() => continueRender(handle));
  }, [handle, lang]);
};
