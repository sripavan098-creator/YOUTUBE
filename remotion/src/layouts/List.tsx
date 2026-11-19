import { AbsoluteFill, Audio, Img, staticFile } from 'remotion';
import { Brand, Caption } from '../Caption';
import { useActiveChunk, useNow } from '../captions';
import { fontFor } from '../fonts';
import type { ShortProps } from '../ShortProps';

export const ShortList = (p: ShortProps) => {
  const t = useNow();
  const active = useActiveChunk(p.words);

  return (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12', fontFamily: fontFor(p.lang) }}>
      {p.shots[0] && (
        <Img
          src={staticFile(p.shots[0])}
          style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.35 }}
        />
      )}
      <AbsoluteFill
        style={{
          background: 'linear-gradient(180deg,rgba(14,14,18,.75),rgba(14,14,18,.95))',
        }}
      />
      <div style={{ position: 'absolute', top: 200, left: 80, right: 80 }}>
        <Brand name={p.brandName} color={p.color} />
        <div
          style={{
            color: '#fff',
            fontSize: 58,
            fontWeight: 800,
            marginTop: 30,
            lineHeight: 1.2,
            textShadow: '0 4px 16px rgba(0,0,0,.9)',
          }}
        >
          {p.headline}
        </div>
      </div>
      <Caption words={active} accent={p.accent} t={t} size={62} bottom={450} />
      <Audio src={staticFile(p.audio)} />
    </AbsoluteFill>
  );
};
