import { Composition } from 'remotion';
import { Comp, CompProps } from './Comp';
import { ShortExplainer } from './layouts/Explainer';
import { ShortList } from './layouts/List';
import { ShortTimeline } from './layouts/Timeline';
import { ShortVersus } from './layouts/Versus';
import { ShortProps } from './ShortProps';

const dShort: ShortProps = {
  lang: 'hi',
  brandName: 'Vincodez Tech',
  color: '#FF6B00',
  accent: '#FFD166',
  headline: '',
  cta: '',
  audio: '',
  audioDuration: 30,
  words: [],
  shots: [],
};

const SHORTS = [
  { id: 'ShortList', component: ShortList },
  { id: 'ShortExplainer', component: ShortExplainer },
  { id: 'ShortVersus', component: ShortVersus },
  { id: 'ShortTimeline', component: ShortTimeline },
] as const;

const FPS = 30;

export const RemotionRoot = () => (
  <>
    {SHORTS.map(({ id, component }) => (
      <Composition
        key={id}
        id={id}
        component={component}
        width={1080}
        height={1920}
        fps={FPS}
        durationInFrames={900}
        defaultProps={dShort}
        calculateMetadata={({ props }) => ({
          durationInFrames: Math.max(1, Math.ceil((props.audioDuration + 0.6) * FPS)),
        })}
      />
    ))}
    <Composition
      id="Comp"
      component={Comp}
      width={1080}
      height={1920}
      fps={FPS}
      durationInFrames={300}
      defaultProps={{ items: [] } as CompProps}
      calculateMetadata={({ props }) => ({
        durationInFrames: props.items.reduce((a, b) => a + b.frames, 0) || 300,
      })}
    />
  </>
);
