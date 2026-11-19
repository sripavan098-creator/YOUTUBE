import {
  AbsoluteFill,
  Audio,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { Brand, Caption } from '../Caption';
import { useActiveChunk, useNow } from '../captions';
import { fontFor } from '../fonts';
import type { ShortProps } from '../ShortProps';

export const ShortTimeline = (p: ShortProps) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = useNow();
  const active = useActiveChunk(p.words);
  const progress = durationInFrames > 1 ? frame / (durationInFrames - 1) : 0;

  const shotCount = Math.max(p.shots.length, 1);
  const seg = p.audioDuration / shotCount;
  const idx = Math.min(Math.floor(t / seg), shotCount - 1);

  return (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12', fontFamily: fontFor(p.lang) }}>
      {p.shots.length > 0 && (
        <Img
          src={staticFile(p.shots[idx])}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      )}
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg,rgba(10,10,14,.7),rgba(10,10,14,.2) 50%,rgba(10,10,14,.9))',
        }}
      />
      <div style={{ position: 'absolute', top: 180, left: 80 }}>
        <Brand name={p.brandName} color={p.color} />
      </div>
      <div
        style={{
          position: 'absolute',
          top: 260,
          left: 80,
          right: 80,
          color: '#fff',
          fontSize: 50,
          fontWeight: 800,
          textShadow: '0 4px 16px rgba(0,0,0,.9)',
        }}
      >
        {p.headline}
      </div>
      <div
        style={{
          position: 'absolute',
          top: '48%',
          left: 80,
          right: 80,
          height: 8,
          backgroundColor: 'rgba(255,255,255,.2)',
          borderRadius: 4,
        }}
      >
        <div
          style={{
            width: `${Math.min(Math.max(progress, 0), 1) * 100}%`,
            height: '100%',
            backgroundColor: p.accent,
            borderRadius: 4,
          }}
        />
      </div>
      <Caption words={active} accent={p.accent} t={t} size={66} />
      <Audio src={staticFile(p.audio)} />
    </AbsoluteFill>
  );
};
