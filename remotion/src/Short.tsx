import { useMemo } from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  OffthreadVideo,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { buildChunks, clean, useActiveChunk, useNow } from './captions';
import { fontFor, useFontsReady } from './fonts';
import type { Scene, ShortProps } from './ShortProps';

export type Variant = 'explainer' | 'list' | 'versus' | 'timeline';

const HOOK_SECONDS = 2.5;
const CTA_SECONDS = 2.8;
const SEG_SECONDS = 2.6; // nothing stays on one framing longer than this
const ORIGINS = ['50% 38%', '22% 30%', '78% 62%', '50% 74%', '70% 28%', '30% 70%'];

const STROKE = '#000';

// Fall back to even cuts if a render was started with old-style props (no scenes).
const sceneList = (p: ShortProps, total: number): Scene[] => {
  if (p.scenes && p.scenes.length) return p.scenes;
  const n = Math.max(p.shots.length, 1);
  return p.shots.map((src, i) => ({
    src,
    kind: 'image' as const,
    start: (i * total) / n,
    end: ((i + 1) * total) / n,
  }));
};

// ---------------------------------------------------------------- one scene

const Poster = ({ p, index, text }: { p: ShortProps; index: number; text?: string }) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(circle at ${index % 2 ? '25% 30%' : '75% 35%'}, ${p.color} 0%, #12121a 62%)`,
      justifyContent: 'center',
      alignItems: 'center',
      padding: 90,
    }}
  >
    <div style={{ position: 'absolute', width: 900, height: 900, borderRadius: 450, right: -300, top: 200,
      border: `22px solid ${p.accent}`, opacity: 0.16 }} />
    <div style={{ position: 'absolute', width: 600, height: 600, borderRadius: 300, left: -200, bottom: 300,
      backgroundColor: p.accent, opacity: 0.1 }} />
    {text ? (
      <div style={{
        position: 'relative',
        width: '100%',
        padding: '56px 48px',
        borderRadius: 36,
        backgroundColor: 'rgba(8,8,12,.9)',
        border: `8px solid ${p.accent}`,
        color: '#fff',
        fontSize: text.length > 100 ? 64 : text.length > 65 ? 78 : 92,
        fontWeight: 900,
        lineHeight: 1.35,
        textAlign: 'center',
        boxShadow: `0 28px 80px rgba(0,0,0,.5), 0 0 60px ${p.color}88`,
      }}>
        {text}
      </div>
    ) : null}
  </AbsoluteFill>
);

const SceneView = ({ scene, index, p }: { scene: Scene; index: number; p: ShortProps }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const len = Math.max(1, Math.round((scene.end - scene.start) * fps));

  // Re-frame every ~2.6 s: a cut-in to a different part of the picture, so a still photo
  // reads as 2-3 shots, not one long hold.
  const nSeg = Math.max(1, Math.ceil(len / (SEG_SECONDS * fps)));
  const segLen = len / nSeg;
  const seg = Math.min(nSeg - 1, Math.floor(frame / segLen));
  const local = frame - seg * segLen;

  const punch = spring({ frame: local, fps, config: { damping: 14, stiffness: 240, mass: 0.6 } });
  const punchScale = interpolate(punch, [0, 1], [seg === 0 ? 1.18 : 1.1, 1.0]);
  const drift = interpolate(local, [0, segLen], [1.0, 1.1], { extrapolateRight: 'clamp' });
  const origin = ORIGINS[(index * 2 + seg) % ORIGINS.length];

  // impact shake on turns and payoffs
  const decay = Math.max(0, 1 - frame / 11);
  const sx = scene.shake ? Math.sin(frame * 2.9) * 16 * decay : 0;
  const sy = scene.shake ? Math.cos(frame * 3.7) * 16 * decay : 0;

  const style = {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
    transformOrigin: origin,
    transform: `translate(${sx}px, ${sy}px) scale(${punchScale * drift})`,
    filter: 'contrast(1.14) saturate(1.2) brightness(0.96)',
  };

  const flash =
    index > 0 && seg === 0
      ? interpolate(frame, [0, 5], [0.5, 0], { extrapolateRight: 'clamp' })
      : seg > 0
        ? interpolate(local, [0, 3], [0.22, 0], { extrapolateRight: 'clamp' })
        : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12', overflow: 'hidden' }}>
      {scene.kind === 'poster' || !scene.src ? (
        <div style={{ ...style, filter: 'none' }}>
          <Poster p={p} index={index} text={scene.posterText} />
        </div>
      ) : scene.kind === 'video' ? (
        <OffthreadVideo src={staticFile(scene.src)} muted style={style} />
      ) : (
        <Img src={staticFile(scene.src)} style={style} />
      )}
      <AbsoluteFill style={{ backgroundColor: '#fff', opacity: flash, mixBlendMode: 'screen' }} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- grade: vignette + grain

const NOISE =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.55 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")";

const Grade = () => {
  const frame = useCurrentFrame();
  const jx = (frame * 37) % 300;
  const jy = (frame * 53) % 300;
  return (
    <>
      <AbsoluteFill
        style={{ background: 'radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 52%, rgba(0,0,0,.5) 100%)' }}
      />
      <AbsoluteFill
        style={{ backgroundImage: NOISE, backgroundPosition: `${jx}px ${jy}px`, opacity: 0.07,
          mixBlendMode: 'overlay' }}
      />
    </>
  );
};

// ---------------------------------------------------------------- hook title

const Hook = ({ p }: { p: ShortProps }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 9, stiffness: 230, mass: 0.7 } });
  const fadeOut = interpolate(frame, [HOOK_SECONDS * fps - 8, HOOK_SECONDS * fps], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const text = p.hook || p.headline;
  // a brief RGB-split glitch as it lands: the eye is pulled to it before it can scroll away
  const glitch = frame < 9 ? (9 - frame) * 2.2 : 0;
  const box = {
    fontSize: 112,
    fontWeight: 900,
    lineHeight: 1.12,
    textAlign: 'center' as const,
    padding: '26px 44px',
    borderRadius: 28,
    maxWidth: 940,
  };
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-start', alignItems: 'center', paddingTop: 400 }}>
      <div
        style={{
          position: 'relative',
          transform: `scale(${interpolate(pop, [0, 1], [1.7, 1])}) rotate(${interpolate(pop, [0, 1], [-7, -2])}deg)`,
          opacity: fadeOut * Math.min(1, pop * 2),
        }}
      >
        {glitch > 0 && (
          <>
            <div style={{ ...box, position: 'absolute', inset: 0, color: '#ff2a55', transform: `translateX(${-glitch}px)`,
              mixBlendMode: 'screen', opacity: 0.8 }}>{text}</div>
            <div style={{ ...box, position: 'absolute', inset: 0, color: '#19e6ff', transform: `translateX(${glitch}px)`,
              mixBlendMode: 'screen', opacity: 0.8 }}>{text}</div>
          </>
        )}
        <div
          style={{
            ...box,
            position: 'relative',
            backgroundColor: p.color,
            color: '#fff',
            boxShadow: '0 22px 70px rgba(0,0,0,.6)',
            border: `7px solid ${p.accent}`,
          }}
        >
          {text}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- kinetic word + stat card

const Slam = ({ word, p }: { word: string; p: ShortProps }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 8, stiffness: 300, mass: 0.6 } });
  const out = interpolate(frame, [fps * 0.75, fps * 0.95], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-start', alignItems: 'center', paddingTop: 640 }}>
      <div
        style={{
          fontSize: word.length > 8 ? 150 : 200,
          fontWeight: 900,
          color: p.accent,
          WebkitTextStroke: '16px #000',
          paintOrder: 'stroke fill',
          textShadow: `0 0 50px ${p.color}`,
          transform: `scale(${interpolate(pop, [0, 1], [2.6, 1])}) rotate(${interpolate(pop, [0, 1], [5, -3])}deg)`,
          opacity: out * Math.min(1, pop * 3),
          maxWidth: 980,
          textAlign: 'center',
          lineHeight: 1.1,
        }}
      >
        {word}
      </div>
    </AbsoluteFill>
  );
};

const StatCard = ({ text, p }: { text: string; p: ShortProps }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 10, stiffness: 200, mass: 0.7 } });
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-start', alignItems: 'center', paddingTop: 560 }}>
      <div
        style={{
          transform: `scale(${interpolate(pop, [0, 1], [0.4, 1])})`,
          opacity: Math.min(1, pop * 2),
          backgroundColor: 'rgba(10,10,16,.82)',
          border: `8px solid ${p.accent}`,
          borderRadius: 36,
          padding: '28px 56px',
          boxShadow: `0 0 90px ${p.color}`,
        }}
      >
        <div style={{ fontSize: text.length > 7 ? 130 : 176, fontWeight: 900, color: p.accent, lineHeight: 1.1,
          textAlign: 'center', WebkitTextStroke: '6px #000', paintOrder: 'stroke fill' }}>
          {text}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- captions

const Captions = ({ p, chunks }: { p: ShortProps; chunks: ReturnType<typeof buildChunks> }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = useNow();
  const active = useActiveChunk(chunks);
  const emph = useMemo(() => new Set((p.emphasis || []).map(clean)), [p.emphasis]);
  if (!active) return null;

  const chunkStart = active[0].start;
  const enter = spring({ frame: frame - Math.round(chunkStart * fps), fps,
    config: { damping: 11, stiffness: 280, mass: 0.5 } });

  return (
    <div
      style={{
        position: 'absolute',
        left: 50,
        right: 50,
        bottom: 520, // clear of the Shorts/Reels buttons and caption bar
        textAlign: 'center',
        fontSize: 92,
        fontWeight: 900,
        lineHeight: 1.25,
        transform: `scale(${interpolate(enter, [0, 1], [0.8, 1])})`,
        opacity: Math.min(1, enter * 2),
      }}
    >
      {active.map((w, i) => {
        const on = t >= w.start && t <= w.end + 0.05;
        const key = emph.has(clean(w.text));
        const color = key ? p.color : on ? p.accent : '#fff';
        return (
          <span
            key={i}
            style={{
              color,
              display: 'inline-block',
              margin: '0 12px',
              transform: `scale(${on ? 1.14 : 1}) ${key && on ? 'rotate(-2deg)' : ''}`,
              WebkitTextStroke: '12px #000',
              paintOrder: 'stroke fill',
              textShadow: '0 6px 24px rgba(0,0,0,.85)',
              ...(key ? { filter: `drop-shadow(0 0 22px ${p.color})` } : {}),
            }}
          >
            {w.text}
          </span>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- chrome

const ProgressBar = ({ p }: { p: ShortProps }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const pct = Math.min(1, frame / Math.max(1, durationInFrames - 1));
  return (
    <div style={{ position: 'absolute', top: 110, left: 0, right: 0, height: 10,
      backgroundColor: 'rgba(255,255,255,.18)' }}>
      <div style={{ width: `${pct * 100}%`, height: '100%', backgroundColor: p.accent }} />
    </div>
  );
};

const BrandChip = ({ p }: { p: ShortProps }) => (
  <div
    style={{
      position: 'absolute',
      top: 150,
      left: 60,
      backgroundColor: p.color,
      color: '#fff',
      fontSize: 34,
      fontWeight: 800,
      padding: '8px 24px',
      borderRadius: 14,
    }}
  >
    {p.brandName}
  </div>
);

const Pill = ({ text, p, bottom }: { text: string; p: ShortProps; bottom: number }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 12, stiffness: 200 } });
  return (
    <div
      style={{
        position: 'absolute',
        bottom,
        left: 60,
        right: 60,
        textAlign: 'center',
        transform: `scale(${interpolate(pop, [0, 1], [0.7, 1])})`,
        opacity: pop,
      }}
    >
      <span
        style={{
          backgroundColor: p.color,
          color: '#fff',
          fontSize: 50,
          fontWeight: 800,
          padding: '18px 36px',
          borderRadius: 22,
          display: 'inline-block',
          border: `4px solid ${p.accent}`,
          lineHeight: 1.25,
        }}
      >
        {text}
      </span>
    </div>
  );
};

// ---------------------------------------------------------------- layout flavours

const VariantChrome = ({ variant, p, scenes }: { variant: Variant; p: ShortProps; scenes: Scene[] }) => {
  const t = useNow();
  const idx = Math.max(0, scenes.findIndex((s) => t >= s.start && t < s.end));
  const cur = idx === -1 ? scenes.length - 1 : idx;

  if (variant === 'list') {
    return (
      <div style={{ position: 'absolute', top: 150, right: 60, color: '#fff', fontSize: 40,
        fontWeight: 900, backgroundColor: 'rgba(0,0,0,.55)', padding: '8px 22px',
        borderRadius: 14, border: `3px solid ${p.accent}` }}>
        {cur + 1}/{scenes.length}
      </div>
    );
  }
  if (variant === 'timeline') {
    return (
      <div style={{ position: 'absolute', bottom: 400, left: 80, right: 80, display: 'flex',
        justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ position: 'absolute', left: 0, right: 0, height: 6, top: 9,
          backgroundColor: 'rgba(255,255,255,.25)' }} />
        {scenes.map((_, i) => (
          <div key={i} style={{ width: 24, height: 24, borderRadius: 12, zIndex: 1,
            backgroundColor: i <= cur ? p.accent : 'rgba(255,255,255,.35)',
            border: '3px solid #000', transform: `scale(${i === cur ? 1.5 : 1})` }} />
        ))}
      </div>
    );
  }
  if (variant === 'versus') {
    return (
      <>
        <AbsoluteFill style={{ background: `linear-gradient(90deg, ${p.color}33 0%, transparent 48%, ${p.accent}33 100%)`,
          mixBlendMode: 'overlay' }} />
        <div style={{ position: 'absolute', top: 0, bottom: 0, left: '50%', width: 6,
          backgroundColor: p.accent, opacity: 0.55 }} />
      </>
    );
  }
  return null;
};

// ---------------------------------------------------------------- the video

export const Short = ({ p, variant }: { p: ShortProps; variant: Variant }) => {
  useFontsReady(p.lang);
  const { fps, durationInFrames } = useVideoConfig();
  const total = durationInFrames / fps;
  const scenes = useMemo(() => sceneList(p, total), [p, total]);
  const chunks = useMemo(() => buildChunks(p.words), [p.words]);
  const nudgeAt = Math.round(total * 0.56 * fps);

  return (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12', fontFamily: fontFor(p.lang) }}>
      {scenes.map((s, i) => (
        <Sequence key={i} from={Math.round(s.start * fps)}
          durationInFrames={Math.max(1, Math.round((s.end - s.start) * fps))}>
          <SceneView scene={s} index={i} p={p} />
        </Sequence>
      ))}

      <Grade />

      {/* legibility: darker at the top (title area) and bottom (captions) */}
      <AbsoluteFill style={{ background:
        'linear-gradient(180deg,rgba(8,8,12,.55) 0%,rgba(8,8,12,0) 28%,rgba(8,8,12,0) 52%,rgba(8,8,12,.72) 100%)' }} />

      <VariantChrome variant={variant} p={p} scenes={scenes} />
      <ProgressBar p={p} />
      <BrandChip p={p} />

      {scenes.map((s, i) => {
        const items = [];
        if (s.slam && i > 0) {
          const at = Math.max(s.start, s.slamAt ?? s.start + 0.15);
          items.push(
            <Sequence key={`sl${i}`} from={Math.round(at * fps)} durationInFrames={Math.round(0.95 * fps)}>
              <Slam word={s.slam} p={p} />
            </Sequence>,
          );
        }
        if (s.stat && i > 0) {
          const at = s.start + 0.15;
          const dur = Math.min(2.4, s.end - at);
          items.push(
            <Sequence key={`st${i}`} from={Math.round(at * fps)} durationInFrames={Math.max(1, Math.round(dur * fps))}>
              <StatCard text={s.stat} p={p} />
            </Sequence>,
          );
        }
        return items;
      })}

      <Sequence from={0} durationInFrames={Math.round(HOOK_SECONDS * fps)}>
        <Hook p={p} />
      </Sequence>

      <Captions p={p} chunks={chunks} />

      {p.nudge ? (
        <Sequence from={nudgeAt} durationInFrames={Math.round(2.4 * fps)}>
          <Pill text={p.nudge} p={p} bottom={800} />
        </Sequence>
      ) : null}

      <Sequence from={Math.max(0, durationInFrames - Math.round(CTA_SECONDS * fps))}>
        <Pill text={p.cta} p={p} bottom={330} />
      </Sequence>

      <Audio src={staticFile(p.audio)} />
    </AbsoluteFill>
  );
};
