import { loadFont as deva } from '@remotion/google-fonts/NotoSansDevanagari';
import { loadFont as telu } from '@remotion/google-fonts/NotoSansTelugu';

// loadFont() registers the face and starts fetching it at import time. Without a
// Telugu/Devanagari face the browser falls back to tofu boxes for these scripts.
const devanagari = deva().fontFamily;
const telugu = telu().fontFamily;

const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

export const fontFor = (lang: 'hi' | 'te' | 'en'): string => {
  if (lang === 'hi') return `${devanagari}, ${SANS}`;
  if (lang === 'te') return `${telugu}, ${SANS}`;
  return SANS;
};
