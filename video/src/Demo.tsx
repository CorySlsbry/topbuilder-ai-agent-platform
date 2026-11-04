import React from "react";
import { AbsoluteFill, interpolate, Sequence, useCurrentFrame } from "remotion";

import { VO_TIMING } from "./voTiming";

const INK = "#0a0b0f";
const PANEL = "#12141b";
const ACCENT = "#7ea2ff";
const ACCENT_SOFT = "#a9c0ff";
const GREEN = "#46d3b6";
const AMBER = "#f2b65a";
const TEXT = "#f4f6fb";
const MUTE = "#8b94a7";
const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, system-ui, sans-serif";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const Bg: React.FC = () => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(1300px 760px at 50% 16%, rgba(126,162,255,0.16), transparent 62%), ${INK}`,
    }}
  />
);

// A scene that fades + lifts in, holds, and fades out; exposes its local frame to children.
const Scene: React.FC<{ dur: number; children: (frame: number) => React.ReactNode }> = ({ dur, children }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 14, dur - 16, dur], [0, 1, 1, 0], clamp);
  const y = interpolate(frame, [0, 16], [22, 0], clamp);
  return (
    <AbsoluteFill
      style={{
        opacity,
        transform: `translateY(${y}px)`,
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: 130,
      }}
    >
      {children(frame)}
    </AbsoluteFill>
  );
};

const Eyebrow: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = ACCENT_SOFT }) => (
  <div
    style={{
      color,
      fontFamily: FONT,
      fontSize: 30,
      fontWeight: 600,
      letterSpacing: 7,
      textTransform: "uppercase",
      marginBottom: 30,
    }}
  >
    {children}
  </div>
);

const Big: React.FC<{ children: React.ReactNode; color?: string; size?: number }> = ({
  children,
  color = TEXT,
  size = 156,
}) => (
  <div style={{ color, fontFamily: FONT, fontSize: size, fontWeight: 800, letterSpacing: -3, lineHeight: 1.02 }}>
    {children}
  </div>
);

const Sub: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ color: MUTE, fontFamily: FONT, fontSize: 38, fontWeight: 500, marginTop: 28, maxWidth: 1280, lineHeight: 1.35 }}>
    {children}
  </div>
);

const countInt = (f: number, target: number) => Math.round(interpolate(f, [10, 48], [0, target], clamp));

// Each scene is a frame->node renderer; the Scene wrapper applies the (voice-driven) duration + fades.
const SCENES: ((f: number) => React.ReactNode)[] = [
  // 1 — Title
  () => (
    <div>
      <div style={{ display: "inline-flex", alignItems: "center", gap: 24 }}>
        <div
          style={{
            width: 74,
            height: 74,
            borderRadius: 20,
            background: "rgba(126,162,255,0.15)",
            border: "1px solid rgba(126,162,255,0.4)",
            display: "grid",
            placeItems: "center",
            color: ACCENT,
            fontSize: 40,
          }}
        >
          ✦
        </div>
        <div style={{ color: TEXT, fontFamily: FONT, fontSize: 96, fontWeight: 800, letterSpacing: -2 }}>
          Top Builder AI
        </div>
      </div>
      <Sub>The AI operating layer for ServiceTitan contractors.</Sub>
    </div>
  ),
  // 2 — Booking / after-hours recovery
  (f) => (
    <div>
      <Eyebrow color={GREEN}>Your phones never sleep</Eyebrow>
      <Big color={GREEN}>{"$" + countInt(f, 2895).toLocaleString("en-US")}</Big>
      <Sub>recovered from after-hours calls — 8 jobs booked from 14 inbound, while you slept.</Sub>
    </div>
  ),
  // 3 — Dispatch / drive time saved
  (f) => (
    <div>
      <Eyebrow>Your trucks drive smarter</Eyebrow>
      <Big color={ACCENT_SOFT}>
        {countInt(f, 60)}
        <span style={{ fontSize: 64, color: MUTE }}> min/day</span>
      </Big>
      <Sub>of windshield time eliminated — the right tech, the shortest route, every single day.</Sub>
    </div>
  ),
  // 4 — Documents
  (f) => (
    <div>
      <Eyebrow>Your paperwork files itself</Eyebrow>
      <Big>
        {countInt(f, 9)}
        <span style={{ fontSize: 84, color: MUTE }}> / 12</span>
      </Big>
      <Sub>documents auto-filed to the right customer + ServiceTitan folder. Expiring COIs and signatures flagged.</Sub>
    </div>
  ),
  // 5 — Field quote builder
  (f) => (
    <div>
      <Eyebrow color={GREEN}>Your techs quote on the spot</Eyebrow>
      <Big color={GREEN}>{"$" + interpolate(f, [10, 48], [0, 472.48], clamp).toFixed(2)}</Big>
      <Sub>built on the tech's phone — add or remove services, the total updates live, push the estimate to ServiceTitan.</Sub>
    </div>
  ),
  // 6 — The approval gate
  (f) => {
    const steps: [string, string][] = [
      ["Propose", ACCENT_SOFT],
      ["Approve", AMBER],
      ["Booked ✓", GREEN],
    ];
    return (
      <div>
        <Eyebrow color={AMBER}>And nothing happens without you</Eyebrow>
        <div style={{ display: "flex", gap: 30, justifyContent: "center", marginTop: 16 }}>
          {steps.map(([label, color], i) => {
            const a = interpolate(f, [24 + i * 32, 46 + i * 32], [0, 1], clamp);
            return (
              <div
                key={label}
                style={{
                  opacity: a,
                  transform: `scale(${0.9 + 0.1 * a})`,
                  padding: "26px 48px",
                  borderRadius: 18,
                  border: `1px solid ${color}66`,
                  background: `${color}1f`,
                  color,
                  fontFamily: FONT,
                  fontSize: 46,
                  fontWeight: 700,
                }}
              >
                {label}
              </div>
            );
          })}
        </div>
        <Sub>Every agent action is proposed, approved, then executed — signed, logged, and reversible.</Sub>
      </div>
    );
  },
  // 7 — Agents + CTA
  (f) => {
    const agents = ["Booking", "Dispatch", "Documents", "Workforce", "Financial", "Inventory"];
    return (
      <div>
        <Eyebrow>Six agents. One command center.</Eyebrow>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 22,
            maxWidth: 1160,
            margin: "6px auto 0",
          }}
        >
          {agents.map((a, i) => {
            const ap = interpolate(f, [12 + i * 7, 32 + i * 7], [0, 1], clamp);
            return (
              <div
                key={a}
                style={{
                  opacity: ap,
                  transform: `translateY(${(1 - ap) * 14}px)`,
                  padding: "30px 24px",
                  borderRadius: 20,
                  background: PANEL,
                  border: "1px solid rgba(255,255,255,0.07)",
                  color: TEXT,
                  fontFamily: FONT,
                  fontSize: 42,
                  fontWeight: 700,
                }}
              >
                {a}
              </div>
            );
          })}
        </div>
        <div style={{ color: TEXT, fontFamily: FONT, fontSize: 52, fontWeight: 700, marginTop: 52 }}>
          It runs your back office.
        </div>
        <div
          style={{
            opacity: interpolate(f, [90, 120], [0, 1], clamp),
            color: ACCENT,
            fontFamily: FONT,
            fontSize: 58,
            fontWeight: 800,
            letterSpacing: 1,
            marginTop: 22,
          }}
        >
          topbuilderai.com
        </div>
      </div>
    );
  },
];

export const Demo: React.FC = () => {
  // Scene durations follow the voiceover (generated voTiming) so the picture tracks the narration;
  // fall back to the hand-authored pacing when no voiceover timing is present.
  const DEFAULT_DURS = [120, 150, 150, 150, 150, 180, 210];
  const durs = VO_TIMING?.Demo ?? DEFAULT_DURS;
  const starts = durs.reduce<number[]>((acc, _d, k) => {
    acc.push(k === 0 ? 0 : acc[k - 1] + durs[k - 1]);
    return acc;
  }, []);
  return (
    <AbsoluteFill style={{ background: INK }}>
      <Bg />
      {SCENES.map((render, k) => (
        <Sequence key={k} from={starts[k]} durationInFrames={durs[k]}>
          <Scene dur={durs[k]}>{render}</Scene>
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
