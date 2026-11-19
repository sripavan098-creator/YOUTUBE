import { AbsoluteFill, OffthreadVideo, Sequence, staticFile } from 'remotion';

export type CompProps = { items: { src: string; frames: number }[] };

export const Comp = ({ items }: CompProps) => {
  let cursor = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {items.map((item, i) => {
        const from = cursor;
        cursor += item.frames;
        return (
          <Sequence key={i} from={from} durationInFrames={item.frames}>
            <OffthreadVideo
              src={staticFile(item.src)}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
