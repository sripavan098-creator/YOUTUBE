import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {Gulu} from './Gulu';

export const GULU_ENDCARD_H = 340;

export const GuluEndCard: React.FC<{
  from: number;
  color?: string;
  accent?: string;
  brandName?: string;
  handle?: string;
  cta?: string;
}> = ({from, color = '#22D3EE', accent = '#A3E635', brandName = '', handle = '', cta = ''}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const local = frame - Math.round(from * fps);
  if (local < 0) return null;
  const s = spring({frame: local, fps, config: {damping: 16, mass: 0.8}});
  const y = interpolate(s, [0, 1], [GULU_ENDCARD_H + 40, 0]);
  const uid = React.useId().replace(/[^a-zA-Z0-9]/g, '');
  const scale = width / 1200;

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: GULU_ENDCARD_H,
                   transform: 'translateY(' + y + 'px)'}}>
        <svg width="100%" height={GULU_ENDCARD_H} viewBox="0 0 1200 340" preserveAspectRatio="xMidYMax slice">
          <defs>
            <linearGradient id={uid + 'sky'} x1="0" y1="0" x2="0.3" y2="1">
              <stop offset="0" stopColor="#0B1430" /><stop offset="1" stopColor="#05080F" />
            </linearGradient>
            <linearGradient id={uid + 'arrow'} x1="0" y1="1" x2="1" y2="0">
              <stop offset="0" stopColor={color} /><stop offset="1" stopColor={accent} />
            </linearGradient>
          </defs>
          <rect x="0" y="0" width="1200" height="340" fill={'url(#' + uid + 'sky)'} />
          <g fill="#FFFFFF" opacity="0.55">
            <circle cx="180" cy="40" r="2" /><circle cx="340" cy="26" r="1.6" /><circle cx="520" cy="52" r="2.2" />
            <circle cx="700" cy="30" r="1.8" /><circle cx="880" cy="46" r="2" /><circle cx="1040" cy="24" r="1.6" />
          </g>
          <g stroke={color} strokeWidth="2.4" fill="none" opacity="0.75">
            <path d="M300 210 V96 M300 96 L246 210 M300 96 L354 210 M300 118 L262 210 M300 118 L338 210" />
            <path d="M430 210 V110 M430 110 L386 210 M430 110 L474 210" />
            <path d="M210 210 H520" />
            <rect x="560" y="120" width="42" height="90" /><rect x="612" y="86" width="34" height="124" />
            <rect x="656" y="140" width="30" height="70" />
            <path d="M726 210 V150 h72 v60 M742 210 v-34 a20 20 0 0 1 40 0 v34" />
            <path d="M860 210 v-52 a40 40 0 0 1 80 0 v52 M900 118 v-22" />
            <path d="M842 210 v-70 M958 210 v-70 M836 140 h12 M952 140 h12" />
          </g>
          <g stroke={accent} strokeWidth="1.4" opacity="0.35">
            <path d="M0 250 H1200 M0 276 H1200 M0 306 H1200" />
            <path d="M600 232 L120 340 M600 232 L360 340 M600 232 L600 340 M600 232 L840 340 M600 232 L1080 340" />
          </g>
          <g stroke={'url(#' + uid + 'arrow)'} strokeWidth="9" fill="none" strokeLinecap="round" opacity="0.95">
            <path d="M520 236 C660 220 780 160 900 78" />
            <path d="M880 78 h34 v34" transform="rotate(-38 897 95)" />
          </g>
          <g transform="translate(986 44)">
            <rect x="0" y="0" width="184" height="60" rx="14" fill="#0C1730" stroke={color} strokeWidth="2.5" />
            <text x="92" y="38" textAnchor="middle" fontSize="26" fill="#FFFFFF"
                  fontFamily="Segoe Script, Brush Script MT, cursive">Welcome!</text>
          </g>
          <g transform="translate(986 122)">
            <rect x="0" y="0" width="184" height="76" rx="14" fill="#0C1730" stroke={accent} strokeWidth="2.5" />
            <text x="92" y="30" textAnchor="middle" fontSize="19" fill={accent}
                  fontFamily="Inter, system-ui, sans-serif" fontWeight="800">{cta.slice(0, 22)}</text>
            <text x="92" y="58" textAnchor="middle" fontSize="16" fill="#A9B8DA"
                  fontFamily="Inter, system-ui, sans-serif">{handle.slice(0, 24)}</text>
          </g>
        </svg>
        <div style={{position: 'absolute', left: 26 * scale, bottom: 8, transform: 'scale(' + Math.max(0.5, scale) + ')',
                     transformOrigin: 'bottom left'}}>
          <Gulu pose="point" size={210} fur={color} accent={accent} />
        </div>
        <div style={{position: 'absolute', left: 250 * scale, bottom: 40,
                     fontFamily: 'Inter, system-ui, sans-serif', fontWeight: 800,
                     fontSize: Math.max(20, 34 * scale), color: '#FFFFFF', textShadow: '0 3px 12px #000'}}>
          {brandName}
        </div>
      </div>
    </AbsoluteFill>
  );
};
