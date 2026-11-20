import { loadFont as deva } from '@remotion/google-fonts/NotoSansDevanagari';
import { loadFont as telu } from '@remotion/google-fonts/NotoSansTelugu';

// Load only what the videos use: the bold weights and the script + latin subsets.
// Calling loadFont() with no options fetches every weight x subset (54 files), which is
// slow and can exceed the 30s render timeout on a slow connection.
const weights: ('800' | '900')[] = ['800', '900'];
const devanagari = deva('normal', { weights, subsets: ['devanagari', 'latin'] }).fontFamily;
const telugu = telu('normal', { weights, subsets: ['telugu', 'latin'] }).fontFamily;

const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

export const fontFor = (lang: 'hi' | 'te' | 'en'): string => {
  if (lang === 'hi') return `${devanagari}, ${SANS}`;
  if (lang === 'te') return `${telugu}, ${SANS}`;
  return SANS;
};
