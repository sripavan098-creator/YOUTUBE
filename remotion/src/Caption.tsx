import { AbsoluteFill } from 'remotion';
import type { Word } from './ShortProps';

type Props = {
  words: Word[] | null;
  accent: string;
  t: number;
  size?: number;
  bottom?: number;
};

export const Caption = ({ words, accent, t, size = 62, bottom = 430 }: Props) => {
  if (!words || words.length === 0) return null;
  return (
    <div
      style={{
        position: 'absolute',
        bottom,
        left: 80,
        right: 80,
        textAlign: 'center',
        fontSize: size,
        fontWeight: 800,
        lineHeight: 1.3,
        textShadow: '0 4px 20px rgba(0,0,0,.95)',
      }}
    >
      {words.map((w, i) => (
        <span key={i} style={{ color: t >= w.start && t <= w.end ? accent : '#fff' }}>
          {w.text}{' '}
        </span>
      ))}
    </div>
  );
};

export const Brand = ({ name, color, style }: { name: string; color: string; style?: React.CSSProperties }) => (
  <div
    style={{
      backgroundColor: color,
      color: '#fff',
      padding: '10px 26px',
      borderRadius: 14,
      fontSize: 32,
      fontWeight: 800,
      display: 'inline-block',
      ...style,
    }}
  >
    {name}
  </div>
);

export const Backdrop = ({ src }: { src?: string }) =>
  src ? (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12' }}>
      <img
        src={src}
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        alt=""
      />
    </AbsoluteFill>
  ) : (
    <AbsoluteFill style={{ backgroundColor: '#0E0E12' }} />
  );
