import { AbsoluteFill, Audio, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { Brand, Caption } from '../Caption';
import { useActiveChunk, useNow } from '../captions';
import { fontFor } from '../fonts';
import type { ShortProps } from '../ShortProps';

export const ShortList = (p: ShortProps) => {
  const t = useNow();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const active = useActiveChunk(p.words);

  // Calculate which shot to show (change every 3 seconds)
  const shotDuration = 3 * fps; // 3 seconds per image
  const currentShotIndex = Math.min(
    Math.floor(frame / shotDuration),
    (p.shots?.length || 1) - 1
  );
  const currentShot = p.shots?.[currentShotIndex] || p.shots?.[0];

  // Ken Burns effect: slow zoom in from 1.0 to 1.15 over the shot duration
  const shotProgress = (frame % shotDuration) / shotDuration;
  const scale = interpolate(shotProgress, [0, 1], [1.0, 1.15], {
    extrapolateRight: 'clamp',
  });

  // Fade transition between shots
  const fadeProgress = (frame % shotDuration) / shotDuration;
  const opacity = fadeProgress < 0.1
    ? interpolate(fadeProgress, [0, 0.1], [0, 0.45]) // Fade in
    : fadeProgress > 0.9
    ? interpolate(fadeProgress, [0.9, 1], [0.45, 0]) // Fade out
    : 0.45;

  return (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12', fontFamily: fontFor(p.lang) }}>
      {/* Animated background with Ken Burns effect */}
      {currentShot && (
        <Img
          src={staticFile(currentShot)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: `scale(${scale})`,
            opacity: opacity,
            transition: 'transform 0.1s linear',
          }}
        />
      )}

      {/* Gradient overlay */}
      <AbsoluteFill
        style={{
          background: 'linear-gradient(180deg,rgba(14,14,18,.75),rgba(14,14,18,.95))',
        }}
      />

      {/* Headline section */}
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

      {/* Dynamic captions */}
      <Caption words={active} accent={p.accent} t={t} size={62} bottom={450} />

      {/* Audio */}
      <Audio src={staticFile(p.audio)} />
    </AbsoluteFill>
  );
};
