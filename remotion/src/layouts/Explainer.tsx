import { AbsoluteFill, Audio, Img, interpolate, staticFile, useVideoConfig } from 'remotion';
import { Brand, Caption } from '../Caption';
import { useActiveChunk, useNow } from '../captions';
import { fontFor } from '../fonts';
import type { ShortProps } from '../ShortProps';

export const ShortExplainer = (p: ShortProps) => {
  const { fps, durationInFrames } = useVideoConfig();
  const t = useNow();
  const active = useActiveChunk(p.words);

  const shotCount = Math.max(p.shots.length, 1);
  const seg = p.audioDuration / shotCount;
  const idx = Math.min(Math.floor(t / seg), shotCount - 1);
  const scale = interpolate(t - idx * seg, [0, seg], [1.06, 1.18], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12', fontFamily: fontFor(p.lang) }}>
      {p.shots.length > 0 && (
        <Img
          src={staticFile(p.shots[idx])}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: `scale(${scale})`,
          }}
        />
      )}
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg,rgba(10,10,14,.6) 0%,rgba(10,10,14,.05) 35%,rgba(10,10,14,.8) 100%)',
        }}
      />
      <div style={{ position: 'absolute', top: 210, left: 80 }}>
        <Brand name={p.brandName} color={p.color} style={{ fontSize: 34 }} />
      </div>
      <div
        style={{
          position: 'absolute',
          top: 300,
          left: 80,
          right: 80,
          color: '#fff',
          fontSize: 52,
          fontWeight: 800,
          lineHeight: 1.3,
          textShadow: '0 4px 16px rgba(0,0,0,.9)',
        }}
      >
        {p.headline}
      </div>
      <Caption words={active} accent={p.accent} t={t} size={66} />
      {t > p.audioDuration && (
        <AbsoluteFill
          style={{
            justifyContent: 'center',
            alignItems: 'center',
            backgroundColor: 'rgba(14,14,18,.85)',
          }}
        >
          <div
            style={{
              backgroundColor: p.color,
              color: '#fff',
              fontSize: 58,
              fontWeight: 800,
              padding: '36px 48px',
              borderRadius: 24,
              maxWidth: 880,
              textAlign: 'center',
            }}
          >
            {p.cta}
          </div>
        </AbsoluteFill>
      )}
      <Audio src={staticFile(p.audio)} />
    </AbsoluteFill>
  );
};
