import { Img, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export const KenBurnsImage = ({ src }: { src: string }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const scale = interpolate(
    frame,
    [0, durationInFrames],
    [1, 1.15],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <Img
      src={src}
      style={{
        width: "100%",
        height: "100%",
        objectFit: "cover",
        transform: `scale(${scale})`,
      }}
    />
  );
};
