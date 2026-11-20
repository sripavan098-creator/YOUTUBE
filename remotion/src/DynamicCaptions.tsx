import { interpolate, useCurrentFrame } from "remotion";

export const DynamicCaptions = ({
  text,
  startFrame,
  duration,
}: {
  text: string;
  startFrame: number;
  duration: number;
}) => {
  const frame = useCurrentFrame();

  const words = text.split(" ");
  const progress = interpolate(
    frame,
    [startFrame, startFrame + duration],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const visibleCount = Math.max(1, Math.floor(progress * words.length));
  const visibleWords = words.slice(0, visibleCount);
  const lastWord = visibleWords[visibleWords.length - 1] || "";
  const preceding = visibleWords.slice(0, -1).join(" ");

  return (
    <div
      style={{
        position: "absolute",
        bottom: "15%",
        left: "50%",
        transform: "translateX(-50%)",
        textAlign: "center",
        fontSize: 52,
        fontWeight: 900,
        fontFamily: "Montserrat, sans-serif",
        color: "white",
        WebkitTextStroke: "2px black",
        textShadow: "4px 4px 0px rgba(0,0,0,0.5)",
        width: "90%",
        lineHeight: 1.2,
      }}
    >
      <span>{preceding ? preceding + " " : ""}</span>
      <span style={{ color: "#FFD700" }}>{lastWord}</span>
    </div>
  );
};
