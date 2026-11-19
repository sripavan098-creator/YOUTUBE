import { AbsoluteFill, Audio, Img, staticFile } from 'remotion';
import { Brand, Caption } from '../Caption';
import { useActiveChunk, useNow } from '../captions';
import { fontFor } from '../fonts';
import type { ShortProps } from '../ShortProps';

export const ShortVersus = (p: ShortProps) => {
  const t = useNow();
  const active = useActiveChunk(p.words);

  return (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12', fontFamily: fontFor(p.lang) }}>
      <div style={{ position: 'absolute', top: 0, left: 0, width: '50%', height: '100%' }}>
        {p.shots[0] && (
          <Img
            src={staticFile(p.shots[0])}
            style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.7 }}
          />
        )}
      </div>
      <div style={{ position: 'absolute', top: 0, left: '50%', width: '50%', height: '100%' }}>
        {p.shots[1] && (
          <Img
            src={staticFile(p.shots[1])}
            style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.7 }}
          />
        )}
      </div>
      <AbsoluteFill
        style={{
          background: 'linear-gradient(180deg,rgba(14,14,18,.4),rgba(14,14,18,.95) 70%)',
        }}
      />
      <div style={{ position: 'absolute', top: 180, left: 80, right: 80, textAlign: 'center' }}>
        <Brand name={p.brandName} color={p.color} style={{ fontSize: 30 }} />
        <div
          style={{
            color: '#fff',
            fontSize: 56,
            fontWeight: 800,
            marginTop: 24,
            textShadow: '0 4px 16px rgba(0,0,0,.9)',
          }}
        >
          {p.headline}
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          top: '42%',
          left: '50%',
          width: 10,
          height: '16%',
          backgroundColor: p.accent,
        }}
      />
      <Caption words={active} accent={p.accent} t={t} size={62} />
      <Audio src={staticFile(p.audio)} />
    </AbsoluteFill>
  );
};
