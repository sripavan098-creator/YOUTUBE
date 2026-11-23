import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export type GuluPose = 'wave' | 'point' | 'think' | 'triumph' | 'guide' | 'shrug';

export const POSE_BY_ROLE: Record<string, GuluPose> = {
  hook: 'wave',
  fact: 'point',
  rehook: 'think',
  payoff: 'guide',
  loop: 'shrug',
};

type PoseCfg = {
  armL: number; armR: number; mouth: 'open' | 'smile' | 'small' | 'wavy';
  eyes: 'sparkle' | 'happy' | 'closed' | 'curious'; tilt: number;
  prop: 'none' | 'clipboard' | 'key'; extra: 'none' | 'sparkle' | 'bubbles' | 'stars' | 'question';
  label: string;
};

export const POSES: Record<GuluPose, PoseCfg> = {
  wave:    {armL: 14,  armR: -142, mouth: 'open',  eyes: 'happy',   tilt: -3, prop: 'none',      extra: 'sparkle',  label: 'Waving & Smiling'},
  point:   {armL: 20,  armR: -96,  mouth: 'smile', eyes: 'sparkle', tilt: 0,  prop: 'none',      extra: 'none',     label: 'Pointing Forward'},
  think:   {armL: 10,  armR: -30,  mouth: 'small', eyes: 'curious', tilt: 6,  prop: 'none',      extra: 'bubbles',  label: 'Deep in Thought'},
  triumph: {armL: 158, armR: -158, mouth: 'open',  eyes: 'closed',  tilt: 0,  prop: 'none',      extra: 'stars',    label: 'Triumphant Celebration'},
  guide:   {armL: 44,  armR: -64,  mouth: 'smile', eyes: 'sparkle', tilt: -2, prop: 'clipboard', extra: 'none',     label: 'Guiding with Clipboard'},
  shrug:   {armL: 78,  armR: -78,  mouth: 'wavy',  eyes: 'curious', tilt: 8,  prop: 'none',      extra: 'question', label: 'Curious Shrug'},
};

const shade = (hex: string, amt: number): string => {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(full, 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) =>
    Math.max(0, Math.min(255, Math.round(v + amt)))
  );
  return '#' + ch.map((v) => v.toString(16).padStart(2, '0')).join('');
};

export const Gulu: React.FC<{
  pose?: GuluPose;
  size?: number;
  fur?: string;
  accent?: string;
  cap?: boolean;
  badge?: boolean;
  animate?: boolean;
}> = ({pose = 'wave', size = 200, fur = '#22D3EE', accent = '#A3E635', cap = true, badge = true, animate = true}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = animate ? frame / fps : 0;
  const P = POSES[pose] ?? POSES.wave;
  const uid = React.useId().replace(/[^a-zA-Z0-9]/g, '');

  const bob = Math.sin(t * 2.2) * 4;
  const blinkPhase = t % 3.6;
  const blink = blinkPhase < 0.11 ? 0.1 : 1;
  const tassel = Math.sin(t * 1.9) * 9;
  const tail = Math.sin(t * 1.5) * 7;
  const waveExtra = pose === 'wave' ? Math.sin(t * 6.5) * 13 : Math.sin(t * 2.6) * 5;
  const cream = '#F7EFE3';
  const dark = shade(fur, -110);
  const body = '#101A33';

  const eye = (cx: number) => {
    if (P.eyes === 'closed' || P.eyes === 'happy') {
      return <path d={'M' + (cx - 15) + ' 146 q15 -20 30 0'} stroke={dark} strokeWidth={7} fill="none" strokeLinecap="round" />;
    }
    const r = P.eyes === 'curious' ? 15 : 18;
    const dy = P.eyes === 'curious' ? -3 : 0;
    return (
      <g>
        <ellipse cx={cx} cy={140 + dy} rx={r} ry={r + 3} fill={'url(#' + uid + 'iris)'} />
        <ellipse cx={cx} cy={141 + dy} rx={r * 0.45} ry={r * 0.62} fill="#0A1020" />
        <circle cx={cx - 6} cy={133 + dy} r={6} fill="#FFFFFF" opacity={0.96} />
        <circle cx={cx + 6} cy={147 + dy} r={3} fill="#FFFFFF" opacity={0.7} />
      </g>
    );
  };

  const mouth = () => {
    if (P.mouth === 'open') {
      return (
        <g>
          <path d="M144 176 q16 22 32 0 q-16 8 -32 0 z" fill="#2A1420" />
          <path d="M152 186 q8 8 16 0 q-8 5 -16 0 z" fill="#FF6B8A" />
        </g>
      );
    }
    if (P.mouth === 'small') return <ellipse cx={160} cy={180} rx={6} ry={7} fill="#2A1420" />;
    if (P.mouth === 'wavy')
      return <path d="M146 180 q7 -7 14 0 q7 7 14 0" stroke="#2A1420" strokeWidth={4} fill="none" strokeLinecap="round" />;
    return (
      <g>
        <path d="M160 172 v6" stroke="#2A1420" strokeWidth={3.4} strokeLinecap="round" />
        <path d="M148 178 q12 11 12 0" stroke="#2A1420" strokeWidth={3.4} fill="none" strokeLinecap="round" />
        <path d="M160 178 q12 11 12 0" stroke="#2A1420" strokeWidth={3.4} fill="none" strokeLinecap="round" />
      </g>
    );
  };

  const arm = (side: 'L' | 'R') => {
    const sx = side === 'L' ? 112 : 208;
    const ang = (side === 'L' ? P.armL : P.armR) + (side === 'R' ? waveExtra : -waveExtra * 0.5);
    if (pose === 'think' && side === 'R') {
      return (
        <g>
          <path d="M206 224 C214 206 198 194 182 190" stroke={body} strokeWidth={21} fill="none" strokeLinecap="round" />
          <circle cx={180} cy={189} r={13} fill={cream} />
        </g>
      );
    }
    return (
      <g transform={'translate(' + sx + ' 214) rotate(' + ang.toFixed(2) + ')'}>
        <rect x={-11} y={0} width={22} height={58} rx={11} fill={body} stroke={shade(fur, -60)} strokeWidth={2} />
        <circle cx={0} cy={60} r={13} fill={cream} />
        {pose === 'point' && side === 'R' ? <rect x={-4.5} y={68} width={9} height={17} rx={4.5} fill={cream} /> : null}
      </g>
    );
  };

  const extra = () => {
    if (P.extra === 'sparkle')
      return (
        <g fill={accent} opacity={0.9}>
          <path d="M262 96 l4 11 11 4 -11 4 -4 11 -4 -11 -11 -4 11 -4 z" />
          <path d="M56 120 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3 z" opacity={0.7} />
        </g>
      );
    if (P.extra === 'bubbles')
      return (
        <g fill="#FFFFFF" opacity={0.85}>
          <circle cx={244} cy={104} r={7} /><circle cx={262} cy={84} r={10} /><circle cx={284} cy={58} r={14} />
          <text x={284} y={64} textAnchor="middle" fontSize={16} fill={dark} fontFamily="Inter, system-ui, sans-serif" fontWeight={800}>?</text>
        </g>
      );
    if (P.extra === 'stars')
      return (
        <g fill="#FBBF24">
          <path d="M52 84 l5 13 13 5 -13 5 -5 13 -5 -13 -13 -5 13 -5 z" />
          <path d="M270 72 l5 13 13 5 -13 5 -5 13 -5 -13 -13 -5 13 -5 z" />
          <path d="M292 150 l3 9 9 3 -9 3 -3 9 -3 -9 -9 -3 9 -3 z" opacity={0.8} />
        </g>
      );
    if (P.extra === 'question')
      return (
        <text x={272} y={96} fontSize={44} fontWeight={800} fill={accent} fontFamily="Inter, system-ui, sans-serif">?</text>
      );
    return null;
  };

  return (
    <svg width={size} height={size * 1.25} viewBox="0 0 320 400" style={{overflow: 'visible', display: 'block'}}>
      <defs>
        <linearGradient id={uid + 'fur'} x1="0" y1="0" x2="0.3" y2="1">
          <stop offset="0" stopColor={shade(fur, 60)} />
          <stop offset="0.55" stopColor={fur} />
          <stop offset="1" stopColor={shade(fur, -55)} />
        </linearGradient>
        <linearGradient id={uid + 'tail'} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor={fur} />
          <stop offset="1" stopColor={accent} />
        </linearGradient>
        <linearGradient id={uid + 'iris'} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7DD3FC" />
          <stop offset="0.5" stopColor="#2563EB" />
          <stop offset="1" stopColor="#1E1B4B" />
        </linearGradient>
        <linearGradient id={uid + 'body'} x1="0" y1="0" x2="0.2" y2="1">
          <stop offset="0" stopColor="#1B2748" />
          <stop offset="1" stopColor="#0A1020" />
        </linearGradient>
        <linearGradient id={uid + 'cap'} x1="0" y1="0" x2="0.4" y2="1">
          <stop offset="0" stopColor="#243356" />
          <stop offset="1" stopColor="#0B1122" />
        </linearGradient>
      </defs>

      <ellipse cx={160} cy={368} rx={72 - bob} ry={13} fill="#000000" opacity={0.42} />

      <g transform={'translate(0 ' + bob.toFixed(2) + ')'}>
        <g transform={'rotate(' + tail.toFixed(2) + ' 108 300)'}>
          <path d="M110 300 C58 302 30 262 46 222 C56 196 82 190 92 208"
                stroke={'url(#' + uid + 'tail)'} strokeWidth={23} fill="none" strokeLinecap="round" />
          <path d="M110 300 C58 302 30 262 46 222 C56 196 82 190 92 208"
                stroke="#FFFFFF" strokeWidth={7} fill="none" strokeLinecap="round" opacity={0.22} />
        </g>

        <rect x={130} y={310} width={27} height={36} rx={13} fill={body} />
        <rect x={163} y={310} width={27} height={36} rx={13} fill={body} />
        <ellipse cx={143} cy={348} rx={18} ry={9} fill={cream} />
        <ellipse cx={177} cy={348} rx={18} ry={9} fill={cream} />

        {arm('L')}
        {arm('R')}

        <path d="M110 206 C110 196 130 190 160 190 C190 190 210 196 210 206 L216 300 C216 316 196 326 160 326 C124 326 104 316 104 300 Z"
              fill={'url(#' + uid + 'body)'} stroke={shade(fur, -60)} strokeWidth={3} />
        <path d="M132 194 L160 214 L188 194" stroke={accent} strokeWidth={5} fill="none" strokeLinecap="round" />
        <path d="M160 214 V318" stroke={shade(fur, -40)} strokeWidth={2.5} opacity={0.8} />
        {badge ? (
          <g>
            <rect x={138} y={240} width={44} height={36} rx={12} fill="#060B16" stroke={accent} strokeWidth={2.5} />
            <text x={160} y={265} textAnchor="middle" fontSize={19} fontWeight={800} fill={accent}
                  fontFamily="Inter, system-ui, sans-serif">GU</text>
          </g>
        ) : null}

        {P.prop === 'clipboard' ? (
          <g transform="rotate(-10 70 262)">
            <rect x={40} y={228} width={60} height={76} rx={8} fill="#E8EEF8" stroke="#94A3B8" strokeWidth={2} />
            <rect x={58} y={222} width={24} height={12} rx={4} fill="#94A3B8" />
            <rect x={50} y={248} width={40} height={4} rx={2} fill={shade(fur, -20)} />
            <rect x={50} y={260} width={32} height={4} rx={2} fill="#B6C2D4" />
            <rect x={50} y={272} width={38} height={4} rx={2} fill="#B6C2D4" />
            <path d="M50 288 l6 6 12 -13" stroke={accent} strokeWidth={4} fill="none" strokeLinecap="round" />
          </g>
        ) : null}

        <g transform={'rotate(' + P.tilt + ' 160 150)'}>
          <path d="M98 94 L112 42 L148 80 Z" fill={'url(#' + uid + 'fur)'} stroke={dark} strokeWidth={2.5} />
          <path d="M222 94 L208 42 L172 80 Z" fill={'url(#' + uid + 'fur)'} stroke={dark} strokeWidth={2.5} />
          <path d="M110 82 L117 58 L134 78 Z" fill="#FF9EC4" opacity={0.75} />
          <path d="M210 82 L203 58 L186 78 Z" fill="#FF9EC4" opacity={0.75} />

          <ellipse cx={160} cy={136} rx={77} ry={71} fill={cream} stroke={dark} strokeWidth={3} />
          <path d="M84 140 C84 98 118 66 160 66 C202 66 236 98 236 140 C236 152 219 158 199 151 C181 145 178 133 160 133 C142 133 139 145 121 151 C101 158 84 152 84 140 Z"
                fill={'url(#' + uid + 'fur)'} />
          <path d="M96 116 a62 58 0 0 1 32 -34" stroke="#FFFFFF" strokeWidth={6} opacity={0.3} fill="none" strokeLinecap="round" />

          <g transform={'translate(0 ' + (140 * (1 - blink)).toFixed(2) + ') scale(1 ' + blink + ')'}>
            {eye(132)}
            {eye(188)}
          </g>

          <ellipse cx={112} cy={170} rx={12} ry={7} fill="#FF9EC4" opacity={0.35} />
          <ellipse cx={208} cy={170} rx={12} ry={7} fill="#FF9EC4" opacity={0.35} />
          <path d="M154 162 h12 l-6 7 z" fill="#2A1420" />
          {mouth()}
          <g stroke={dark} strokeWidth={2} opacity={0.45} strokeLinecap="round">
            <path d="M118 166 L88 160" /><path d="M118 172 L86 172" /><path d="M118 178 L88 184" />
            <path d="M202 166 L232 160" /><path d="M202 172 L234 172" /><path d="M202 178 L232 184" />
          </g>

          {cap ? (
            <g>
              <path d="M118 76 C118 62 138 54 160 54 C182 54 202 62 202 76 Z" fill={'url(#' + uid + 'cap)'} />
              <path d="M160 32 L252 60 L160 88 L68 60 Z" fill={'url(#' + uid + 'cap)'} stroke={fur} strokeWidth={2.5} />
              <circle cx={160} cy={60} r={6} fill={accent} />
              <g transform={'rotate(' + tassel.toFixed(2) + ' 252 60)'}>
                <path d="M252 60 C266 76 268 96 264 114" stroke={accent} strokeWidth={5} fill="none" strokeLinecap="round" />
                <path d="M258 112 h12 l-3 20 h-6 z" fill={accent} />
              </g>
            </g>
          ) : null}
        </g>
        {extra()}
      </g>
    </svg>
  );
};

export const GuluMark: React.FC<{
  scenes?: Array<{start: number; end: number; role?: string}>;
  color?: string;
  accent?: string;
  brandName?: string;
  mascot?: {size?: number; opacity?: number; show?: boolean; cap?: boolean};
}> = ({scenes = [], color = '#22D3EE', accent = '#A3E635', brandName = '', mascot}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (mascot?.show === false) return null;
  const t = frame / fps;
  const idx = scenes.findIndex((s) => t >= s.start && t < s.end);
  const sc = idx >= 0 ? scenes[idx] : null;
  const pose = POSE_BY_ROLE[sc?.role ?? 'fact'] ?? 'point';
  const since = sc ? t - sc.start : 0;
  const pop = spring({frame: Math.max(0, Math.round(since * fps)), fps, config: {damping: 12, mass: 0.5}});
  const scale = interpolate(pop, [0, 1], [0.82, 1]);
  const fade = interpolate(frame, [0, 9], [0, mascot?.opacity ?? 0.9], {extrapolateRight: 'clamp'});
  const size = mascot?.size ?? 96;

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', top: '3.4%', left: '3.2%', opacity: fade,
                   transform: 'scale(' + scale + ')', transformOrigin: 'top left',
                   display: 'flex', alignItems: 'center', gap: 10}}>
        <Gulu pose={pose} size={size} fur={color} accent={accent} cap={mascot?.cap !== false} />
        <div style={{fontFamily: 'Inter, system-ui, sans-serif', fontWeight: 800,
                     fontSize: Math.round(size * 0.25), color: '#FFFFFF', lineHeight: 1.1,
                     textShadow: '0 3px 10px rgba(0,0,0,.95)'}}>
          {brandName}
          <div style={{fontSize: Math.round(size * 0.15), color: accent, letterSpacing: 2}}>GULU</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
