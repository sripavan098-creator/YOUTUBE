export type Word = { text: string; start: number; end: number };

export type Scene = {
  src: string;
  kind: 'video' | 'image';
  start: number; // seconds
  end: number; // seconds
};

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
  // v3 fields. All optional so props written by older renders still load.
  hook?: string;
  emphasis?: string[];
  scenes?: Scene[];
};
