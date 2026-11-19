export type Word = { text: string; start: number; end: number };

export type ShortProps = {
  lang: 'hi' | 'te' | 'en';
  brandName: string;
  color: string;
  accent: string;
  headline: string;
  cta: string;
  audio: string;
  audioDuration: number;
  words: Word[];
  shots: string[];
};
