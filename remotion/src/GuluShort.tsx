import React from 'react';
import {
  AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, CalculateMetadataFunction,
  interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import {GuluMark} from './Gulu';
import {GuluCelebration} from './GuluCelebration';
import {GuluEndCard, GULU_ENDCARD_H} from './GuluEndCard';

type Word = {text: string; start: number; end?: number};
type Scene = {
  start: number; end: number; src: string; kind: 'image' | 'video' | 'poster';
  role?: string; shake?: boolean; slam?: string; slamAt?: number; stat?: string;
  posterText?: string; posterKeyword?: string;
};

export type GuluShortProps = {
  lang: string; brandName: string; color: string; accent: string;
  headline: string; hook: string; emphasis: string[]; cta: string;
  audio: string; audioDuration: number; words: Word[]; nudge?: string;
  scenes: Scene[]; shots?: string[];
  handle?: string;
  mascot?: {size?: number; opacity?: number; show?: boolean; cap?: boolean};
  endCard?: boolean;
};

const TAIL = 0.6;
const STRIP = '.,!?।…"\'“”‘’():;-–—';
const clean = (s: string) => s.split('').filter((c) => STRIP.indexOf(c) === -1).join('');

export const calculateGuluMetadata: CalculateMetadataFunction<GuluShortProps> = ({props}) => {
  const dur = Number(props.audioDuration) || 10;
  return {durationInFrames: Math.max(30, Math.ceil((dur + TAIL) * 30)), fps: 30, width: 1080, height: 1920};
};

const SUCCESS: Record<string, string> = {te: 'ధృవీకరించబడింది!', hi: 'वेरिफ़ाई सक्सेस!', en: 'Verified!'};

const TopicMark: React.FC<{keyword: string; color: string; accent: string}> = ({keyword, color, accent}) => {
  const q = keyword.toLowerCase();
  const kind = /phone|mobile|smartphone|device/.test(q) ? 'device'
    : /payment|money|rupee|bank|upi|finance/.test(q) ? 'finance'
      : /security|privacy|scam|fraud|hack|password/.test(q) ? 'security'
        : /ai|robot|chip|processor|software|data/.test(q) ? 'tech' : 'topic';

  return (
    <svg width="230" height="230" viewBox="0 0 230 230" role="img" aria-label={keyword || 'topic illustration'}>
      <circle cx="115" cy="115" r="104" fill={color} opacity="0.22" />
      <circle cx="115" cy="115" r="82" fill="#07101E" stroke={accent} strokeWidth="5" />
      {kind === 'device' ? (
        <g fill="none" stroke={accent} strokeWidth="9" strokeLinejoin="round">
          <rect x="78" y="52" width="74" height="126" rx="14" />
          <path d="M101 67h28M105 159h20" strokeLinecap="round" />
        </g>
      ) : null}
      {kind === 'finance' ? (
        <g fill="none" stroke={accent} strokeWidth="9">
          <circle cx="115" cy="115" r="48" />
          <path d="M136 91c-8-10-37-12-40 5-4 22 39 12 39 34-1 19-29 22-43 8M115 74v82" strokeLinecap="round" />
        </g>
      ) : null}
      {kind === 'security' ? (
        <path d="M115 64 158 81v35c0 31-20 49-43 61-23-12-43-30-43-61V81z"
              fill="none" stroke={accent} strokeWidth="9" strokeLinejoin="round" />
      ) : null}
      {kind === 'tech' ? (
        <g fill="none" stroke={accent} strokeWidth="8" strokeLinejoin="round">
          <rect x="76" y="76" width="78" height="78" rx="12" />
          <path d="M92 60v16m23-16v16m23-16v16M92 154v16m23-16v16m23-16v16M60 92h16m-16 23h16m-16 23h16m78-46h16m-16 23h16m-16 23h16" />
          <path d="m99 116 11 11 22-25" strokeLinecap="round" />
        </g>
      ) : null}
      {kind === 'topic' ? (
        <g fill="none" stroke={accent} strokeWidth="8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M70 154 105 82l20 42 17-28 25 58z" />
          <circle cx="151" cy="79" r="12" fill={accent} />
        </g>
      ) : null}
    </svg>
  );
};

export const GuluShort: React.FC<GuluShortProps> = (props) => {
  const {
    lang, brandName, color, accent, headline, hook, emphasis = [], cta,
    audio, audioDuration, words = [], scenes = [], mascot, handle,
  } = props;
  const frame = useCurrentFrame();
  const {fps, durationInFrames, height} = useVideoConfig();
  const t = frame / fps;

  const idx = scenes.findIndex((s) => t >= s.start && t < s.end);
  const sc = idx >= 0 ? scenes[idx] : scenes[scenes.length - 1];
  const sceneStart = sc ? Math.round(sc.start * fps) : 0;
  const sceneLen = sc ? Math.max(1, Math.round((sc.end - sc.start) * fps)) : durationInFrames;
  const localF = frame - sceneStart;

  const zoomIn = idx % 2 === 0;
  const zoom = interpolate(localF, [0, sceneLen], zoomIn ? [1.04, 1.14] : [1.14, 1.04], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  const shakeOn = sc?.shake && localF < 14;
  const amp = shakeOn ? interpolate(localF, [0, 14], [12, 0], {extrapolateRight: 'clamp'}) : 0;
  const sx = amp * Math.sin(localF * 2.3);
  const sy = amp * Math.cos(localF * 3.1);

  const lines: Array<{words: Word[]; start: number; end: number}> = [];
  let buf: Word[] = [];
  words.forEach((w) => {
    buf.push(w);
    const ends = /[.!?।…]$/.test(w.text || '');
    if (buf.length >= 4 || ends) {
      lines.push({words: buf, start: buf[0].start, end: (buf[buf.length - 1].end ?? buf[buf.length - 1].start + 0.4)});
      buf = [];
    }
  });
  if (buf.length) lines.push({words: buf, start: buf[0].start, end: buf[buf.length - 1].end ?? buf[buf.length - 1].start + 0.4});
  const line = lines.find((l) => t >= l.start - 0.06 && t < l.end + 0.22);

  const emph = new Set(emphasis.map(clean));
  const hookIn = spring({frame, fps, config: {damping: 12, mass: 0.6}});
  const hookOut = interpolate(t, [2.1, 2.45], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const showHook = t < 2.45 && hook;

  const endFrom = Math.max(0, audioDuration + TAIL - 2.4);
  const endOn = props.endCard !== false && t >= endFrom;
  const capBottom = endOn ? Math.round((GULU_ENDCARD_H / height) * 100) + 4 : 24;

  const slamAt = sc?.slamAt;
  const slamOn = sc?.slam && slamAt !== undefined && t >= slamAt && t < slamAt + 0.55;
  const slamP = slamOn ? spring({frame: Math.round((t - (slamAt as number)) * fps), fps, config: {damping: 10, mass: 0.5}}) : 0;

  const statIn = sc?.stat ? spring({frame: Math.max(0, localF - 4), fps, config: {damping: 14}}) : 0;
  const payoff = scenes.find((s) => s.role === 'payoff');

  return (
    <AbsoluteFill style={{backgroundColor: '#05070D'}}>
      <AbsoluteFill style={{transform: 'translate(' + sx + 'px,' + sy + 'px)'}}>
        {sc && sc.src && sc.kind === 'video' ? (
          <Sequence from={sceneStart} durationInFrames={sceneLen}>
            <OffthreadVideo src={staticFile(sc.src)} muted
                            style={{width: '100%', height: '100%', objectFit: 'cover', transform: 'scale(' + zoom + ')'}} />
          </Sequence>
        ) : null}
        {sc && sc.src && sc.kind === 'image' ? (
          <Img src={staticFile(sc.src)}
               style={{width: '100%', height: '100%', objectFit: 'cover', transform: 'scale(' + zoom + ')'}} />
        ) : null}
        {(!sc || !sc.src || sc.kind === 'poster') ? (
          <AbsoluteFill style={{background: 'radial-gradient(70% 60% at 40% 25%, ' + color + '88, transparent 70%), radial-gradient(60% 50% at 75% 80%, ' + accent + '66, transparent 72%), #101A33',
                                justifyContent: 'center', alignItems: 'center', padding: 80}}>
            <div style={{position: 'relative', width: '100%', display: 'flex', flexDirection: 'column',
                         alignItems: 'center', gap: 24}}>
              <TopicMark keyword={sc?.posterKeyword ?? ''} color={color} accent={accent} />
              {sc?.posterKeyword ? (
                <div style={{padding: '10px 24px', borderRadius: 999, border: '2px solid ' + accent,
                             color: accent, background: 'rgba(5, 10, 22, .72)', fontSize: 28,
                             fontFamily: 'Inter, system-ui, sans-serif', fontWeight: 800,
                             letterSpacing: 2, textTransform: 'uppercase', textAlign: 'center'}}>
                  {sc.posterKeyword}
                </div>
              ) : null}
              {sc?.posterText ? (
                <div style={{maxWidth: '100%', padding: '34px 40px', borderRadius: 28,
                             border: '3px solid ' + accent, background: 'rgba(5, 10, 22, .82)',
                             color: '#FFFFFF',
                             fontFamily: 'Inter, Noto Sans Telugu, Noto Sans Devanagari, system-ui, sans-serif',
                             fontSize: 58, fontWeight: 800, lineHeight: 1.28, textAlign: 'center',
                             textShadow: '0 4px 18px rgba(0,0,0,.8)'}}>
                  {sc.posterText}
                </div>
              ) : null}
            </div>
          </AbsoluteFill>
        ) : null}
        <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(4,7,14,.72) 0%, rgba(4,7,14,.12) 26%, rgba(4,7,14,.28) 58%, rgba(4,7,14,.86) 100%)'}} />
      </AbsoluteFill>

      <div style={{position: 'absolute', top: 16, left: 24, right: 24, height: 5, borderRadius: 99, background: 'rgba(255,255,255,.22)'}}>
        <div style={{height: '100%', width: (frame / durationInFrames) * 100 + '%', borderRadius: 99,
                     background: 'linear-gradient(90deg,' + color + ',' + accent + ')'}} />
      </div>

      {showHook ? (
        <div style={{position: 'absolute', top: '15%', left: '50%',
                     transform: 'translate(-50%,-50%) scale(' + interpolate(hookIn, [0, 1], [0.7, 1]) + ')',
                     opacity: hookOut, background: 'linear-gradient(120deg,' + color + ',' + accent + ')',
                     color: '#06121A', padding: '18px 34px', borderRadius: 20, border: '4px solid rgba(255,255,255,.92)',
                     fontFamily: 'Inter, Noto Sans Telugu, Noto Sans Devanagari, system-ui, sans-serif',
                     fontWeight: 800, fontSize: 62, whiteSpace: 'nowrap',
                     boxShadow: '0 22px 50px -16px rgba(0,0,0,.9)'}}>
          {hook}
        </div>
      ) : null}

      {sc?.stat ? (
        <div style={{position: 'absolute', top: '30%', left: '50%',
                     transform: 'translate(-50%,-50%) scale(' + interpolate(statIn, [0, 1], [0.6, 1]) + ')',
                     opacity: statIn, background: '#060B16', border: '4px solid ' + accent,
                     borderRadius: 22, padding: '12px 30px', color: '#FFFFFF',
                     fontFamily: 'Inter, system-ui, sans-serif', fontWeight: 800, fontSize: 84,
                     boxShadow: '0 0 60px -10px ' + accent}}>
          {sc.stat}
        </div>
      ) : null}

      {slamOn ? (
        <div style={{position: 'absolute', top: '46%', left: '50%',
                     transform: 'translate(-50%,-50%) scale(' + interpolate(slamP, [0, 1], [1.6, 1]) + ') rotate(-4deg)',
                     opacity: interpolate(t - (slamAt as number), [0, 0.08, 0.42, 0.55], [0, 1, 1, 0]),
                     color: accent, fontFamily: 'Inter, Noto Sans Telugu, Noto Sans Devanagari, system-ui, sans-serif',
                     fontWeight: 800, fontSize: 128, WebkitTextStroke: '5px #000', textShadow: '0 0 50px ' + accent}}>
          {sc?.slam}
        </div>
      ) : null}

      {line ? (
        <div style={{position: 'absolute', left: 40, right: 40, bottom: capBottom + '%', textAlign: 'center',
                     fontFamily: 'Inter, Noto Sans Telugu, Noto Sans Devanagari, system-ui, sans-serif',
                     fontWeight: 800, fontSize: 60, lineHeight: 1.32, WebkitTextStroke: '2.5px #000',
                     textShadow: '0 4px 0 #000, 0 0 26px rgba(0,0,0,.95)'}}>
          {line.words.map((w, i) => {
            const active = t >= w.start - 0.03 && t < (w.end ?? w.start + 0.35) + 0.05;
            const isEmph = emph.has(clean(w.text || ''));
            return (
              <span key={i} style={{color: active ? accent : isEmph ? color : '#FFFFFF',
                                    display: 'inline-block', margin: '0 8px',
                                    transform: active ? 'scale(1.08)' : 'scale(1)'}}>
                {w.text}
              </span>
            );
          })}
        </div>
      ) : null}

      <GuluMark scenes={scenes} color={color} accent={accent} brandName={brandName} mascot={mascot} />

      {payoff ? (
        <GuluCelebration at={payoff.start + 0.1} color={color} accent={accent}
                         label={SUCCESS[lang] ?? SUCCESS.en} count={70} />
      ) : null}

      {endOn ? (
        <GuluEndCard from={endFrom} color={color} accent={accent} brandName={brandName}
                     handle={handle ?? ''} cta={cta} />
      ) : null}

      <Audio src={staticFile(audio)} />
    </AbsoluteFill>
  );
};
