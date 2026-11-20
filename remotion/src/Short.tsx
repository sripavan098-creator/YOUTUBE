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
import { fontFor } from './fonts';
import type { Scene, ShortProps } from './ShortProps';

export type Variant = 'explainer' | 'list' | 'versus' | 'timeline';

const HOOK_SECONDS = 2.4;
const CTA_SECONDS = 2.8;

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

const SceneView = ({ scene, index }: { scene: Scene; index: number }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const len = Math.max(1, Math.round((scene.end - scene.start) * fps));

  // Every cut lands with a quick punch-in, then a slow drift (alternating direction) so
  // even a still photo never sits dead on screen.
  const punch = spring({ frame, fps, config: { damping: 14, stiffness: 220, mass: 0.6 } });
  const punchScale = interpolate(punch, [0, 1], [1.16, 1.0]);
  const dir = index % 2 === 0 ? [1.0, 1.07] : [1.07, 1.0];
  const drift = interpolate(frame, [0, len], dir, { extrapolateRight: 'clamp' });
  const style = {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
    transform: `scale(${punchScale * drift})`,
  };

  return (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12', overflow: 'hidden' }}>
      {scene.kind === 'video' ? (
        <OffthreadVideo src={staticFile(scene.src)} muted style={style} />
      ) : (
        <Img src={staticFile(scene.src)} style={style} />
      )}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- hook title

const Hook = ({ p }: { p: ShortProps }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 11, stiffness: 180 } });
  const fadeOut = interpolate(frame, [HOOK_SECONDS * fps - 8, HOOK_SECONDS * fps], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-start', alignItems: 'center', paddingTop: 430 }}>
      <div
        style={{
          transform: `scale(${interpolate(pop, [0, 1], [0.6, 1])}) rotate(${interpolate(pop, [0, 1], [-4, -2])}deg)`,
          opacity: fadeOut * Math.min(1, pop * 1.5),
          backgroundColor: p.color,
          color: '#fff',
          fontSize: 104,
          fontWeight: 900,
          lineHeight: 1.15,
          textAlign: 'center',
          padding: '26px 44px',
          borderRadius: 28,
          maxWidth: 940,
          boxShadow: '0 18px 60px rgba(0,0,0,.55)',
          border: `6px solid ${p.accent}`,
        }}
      >
        {p.hook || p.headline}
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
    config: { damping: 12, stiffness: 260, mass: 0.5 } });

  return (
    <div
      style={{
        position: 'absolute',
        left: 60,
        right: 60,
        bottom: 520, // clear of the Shorts/Reels buttons and caption bar
        textAlign: 'center',
        fontSize: 88,
        fontWeight: 900,
        lineHeight: 1.22,
        transform: `scale(${interpolate(enter, [0, 1], [0.86, 1])})`,
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
              transform: `scale(${on ? 1.12 : 1})`,
              WebkitTextStroke: '10px #000',
              paintOrder: 'stroke fill',
              textShadow: '0 6px 24px rgba(0,0,0,.8)',
              ...(key ? { filter: `drop-shadow(0 0 18px ${p.color})` } : {}),
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

const Cta = ({ p }: { p: ShortProps }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 12, stiffness: 200 } });
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 330,
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
        }}
      >
        {p.cta}
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
  const { fps, durationInFrames } = useVideoConfig();
  const total = durationInFrames / fps;
  const scenes = useMemo(() => sceneList(p, total), [p, total]);
  const chunks = useMemo(() => buildChunks(p.words), [p.words]);

  return (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12', fontFamily: fontFor(p.lang) }}>
      {scenes.map((s, i) => (
        <Sequence key={i} from={Math.round(s.start * fps)}
          durationInFrames={Math.max(1, Math.round((s.end - s.start) * fps))}>
          <SceneView scene={s} index={i} />
        </Sequence>
      ))}

      {/* legibility: darker at the top (title area) and bottom (captions) */}
      <AbsoluteFill style={{ background:
        'linear-gradient(180deg,rgba(8,8,12,.55) 0%,rgba(8,8,12,0) 28%,rgba(8,8,12,0) 52%,rgba(8,8,12,.72) 100%)' }} />

      <VariantChrome variant={variant} p={p} scenes={scenes} />
      <ProgressBar p={p} />
      <BrandChip p={p} />

      <Sequence from={0} durationInFrames={Math.round(HOOK_SECONDS * fps)}>
        <Hook p={p} />
      </Sequence>

      <Captions p={p} chunks={chunks} />

      <Sequence from={Math.max(0, durationInFrames - Math.round(CTA_SECONDS * fps))}>
        <Cta p={p} />
      </Sequence>

      <Audio src={staticFile(p.audio)} />
    </AbsoluteFill>
  );
};
