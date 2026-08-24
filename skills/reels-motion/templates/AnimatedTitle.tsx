/**
 * Анимированный титул рубрики: мелкая строка сверху, огромная цифра или слово,
 * мелкая строка снизу. Появляется с пружиной, уходит вверх.
 *
 * Рендер прозрачным слоем:
 *   npx remotion render --image-format=png --pixel-format=yuva444p10le \
 *     --codec=prores --prores-profile=4444 AnimatedTitle титул.mov
 */
import React from "react";
import {
  AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig,
} from "remotion";

export type TitleProps = {
  top: string;
  main: string;
  bottom: string;
  accent: string;      // #FF7A00 — тот же акцент, что в styles.json
  outFrame: number;    // кадр, на котором титул начинает уезжать
};

export const AnimatedTitle: React.FC<TitleProps> = ({
  top, main, bottom, accent, outFrame,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // пружина с лёгким перелётом — от неё появление выглядит живым
  const pop = spring({ frame, fps, config: { damping: 12, stiffness: 180, mass: 0.7 } });
  const rise = spring({ frame: frame - 3, fps, config: { damping: 14 } });
  const leave = interpolate(frame, [outFrame, outFrame + 8], [0, -160],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const fade = interpolate(frame, [outFrame, outFrame + 8], [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const stroke = "12px #000";
  const shadow = "0 10px 28px rgba(0,0,0,.55)";

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center", alignItems: "center",
        fontFamily: "HSE Sans, Unbounded, sans-serif",
        textTransform: "uppercase", textAlign: "center",
        transform: `translateY(${leave}px)`, opacity: fade,
      }}
    >
      <div style={{ transform: `scale(${pop})` }}>
        <div style={{ fontSize: 58, color: "#fff", WebkitTextStroke: "6px #000",
                      paintOrder: "stroke", textShadow: shadow, letterSpacing: 1 }}>
          {top}
        </div>
        <div style={{ fontSize: 210, lineHeight: 1, color: accent,
                      WebkitTextStroke: stroke, paintOrder: "stroke",
                      textShadow: shadow,
                      transform: `translateY(${interpolate(rise, [0, 1], [40, 0])}px)` }}>
          {main}
        </div>
        <div style={{ fontSize: 58, color: "#fff", WebkitTextStroke: "6px #000",
                      paintOrder: "stroke", textShadow: shadow, letterSpacing: 1 }}>
          {bottom}
        </div>
      </div>
    </AbsoluteFill>
  );
};
