export type Word = { text: string; start: number; end: number };

export type Scene = {
  src: string; // '' means: no photo, draw a designed poster instead
  kind: 'video' | 'image' | 'poster';
  start: number; // seconds
  end: number; // seconds
  // v4 director fields, all optional
  role?: 'hook' | 'fact' | 'rehook' | 'payoff' | 'loop';
  slam?: string; // one word thrown huge on screen
  slamAt?: number; // seconds, when that word is spoken
  stat?: string; // a big number / short phrase shown as a card
  shake?: boolean; // camera impact
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
  hook?: string;
  emphasis?: string[];
  scenes?: Scene[];
  nudge?: string; // value-first follow prompt shown mid-video
};
