import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {Gulu} from './Gulu';

const COLORS = ['#22D3EE', '#A3E635', '#FBBF24', '#FF2D95', '#8B5CF6', '#F7EFE3'];

const rnd = (i: number, salt: number): number => {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453;
  return x - Math.floor(x);
};

export const GuluCelebration: React.FC<{
  at: number;
  duration?: number;
  color?: string;
  accent?: string;
  label?: string;
  count?: number;
}> = ({at, duration = 1.6, color = '#22D3EE', accent = '#A3E635', label = '', count = 70}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const start = Math.round(at * fps);
  const local = frame - start;
  const life = Math.round(duration * fps);
  if (local < 0 || local > life) return null;

  const p = local / fps;
  const fade = interpolate(local, [0, 6, life - 12, life], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const pop = spring({frame: local, fps, config: {damping: 11, mass: 0.6}});

  const bits = new Array(Math.max(0, Math.round(count))).fill(0).map((_, i) => {
    const x0 = rnd(i, 1) * width;
    const drift = (rnd(i, 2) - 0.5) * 260;
    const y = -60 + p * (height * 0.85) * (0.55 + rnd(i, 3) * 0.7);
    const rot = rnd(i, 4) * 360 + p * (240 + rnd(i, 5) * 420);
    const w = 8 + rnd(i, 6) * 12;
    const h = 12 + rnd(i, 7) * 16;
    return (
      <div key={i} style={{position: 'absolute', left: x0 + drift * p, top: y,
                            width: w, height: h, background: COLORS[i % COLORS.length],
                            transform: 'rotate(' + rot + 'deg)', borderRadius: 2,
                            opacity: 0.95 * fade}} />
    );
  });

  const stars = new Array(9).fill(0).map((_, i) => {
    const a = (i / 9) * Math.PI * 2;
    const r = 130 + p * 210;
    const s = interpolate(local, [0, 8, life], [0, 1.1, 0], {extrapolateRight: 'clamp'});
    return (
      <div key={'s' + i} style={{position: 'absolute', left: width / 2 + Math.cos(a) * r,
                                 top: height * 0.42 + Math.sin(a) * r * 0.7,
                                 fontSize: 40, color: '#FBBF24', opacity: fade,
                                 transform: 'translate(-50%,-50%) scale(' + s + ')'}}>★</div>
    );
  });

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {bits}
      {stars}
      <div style={{position: 'absolute', left: '50%', top: '18%',
                   transform: 'translate(-50%,-50%) scale(' + interpolate(pop, [0, 1], [0.6, 1]) + ')',
                   opacity: fade, display: 'flex', alignItems: 'center', gap: 14,
                   background: 'linear-gradient(120deg,' + color + ',' + accent + ')',
                   padding: '14px 26px', borderRadius: 18, border: '3px solid rgba(255,255,255,.9)',
                   boxShadow: '0 18px 44px -14px rgba(0,0,0,.9)'}}>
        <Gulu pose="triumph" size={78} fur="#FFFFFF" accent="#0B1122" animate={false} />
        <span style={{fontFamily: 'Inter, system-ui, sans-serif', fontWeight: 800, fontSize: 38, color: '#06121A'}}>
          {label}
        </span>
      </div>
    </AbsoluteFill>
  );
};
