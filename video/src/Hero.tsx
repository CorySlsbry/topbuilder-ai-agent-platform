import React from "react";
import { AbsoluteFill, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";

// Above-the-fold HERO sizzle — muted autoplay loop. Three beats:
//   1) the problem  2) how it works (REAL platform screens, captured from the live demo, animating)
//   3) life after the system.  No voiceover. 1920x1080 @ 30fps.

const INK = "#080a0f";
const ACCENT = "#7ea2ff";
const ACCENT_SOFT = "#a9c0ff";
const GREEN = "#46d3b6";
const AMBER = "#f2b65a";
const RED = "#f0846b";
const TEXT = "#f4f6fb";
const MUTE = "#8b94a7";
const INDIGO = "#8390ff";
const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, system-ui, sans-serif";
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const Bg: React.FC<{ tint?: string }> = ({ tint = "rgba(126,162,255,0.16)" }) => (
  <AbsoluteFill
    style={{ background: `radial-gradient(1500px 880px at 50% 8%, ${tint}, transparent 62%), ${INK}` }}
  />
);

// ---- a captured platform screen, in a premium browser card, with a gentle Ken Burns ----
const Screen: React.FC<{
  src: string;
  f: number;
  dur: number;
  from?: number;
  to?: number;
  panY?: number;
}> = ({ src, f, dur, from = 1.0, to = 1.06, panY = -18 }) => {
  const t = interpolate(f, [0, dur], [0, 1], clamp);
  const scale = from + (to - from) * t;
  const y = panY * t;
  const rise = interpolate(f, [0, 16], [26, 0], clamp);
  const op = interpolate(f, [0, 14], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
      <div
        style={{
          width: 1740,
          height: 979,
          borderRadius: 18,
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.10)",
          boxShadow: "0 60px 140px -40px rgba(0,0,0,0.85), 0 0 0 1px rgba(126,162,255,0.06)",
          transform: `translateY(${rise}px)`,
          opacity: op,
          background: "#0b0d12",
        }}
      >
        <Img
          src={staticFile(src)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${scale}) translateY(${y}px)`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

// ---- lower-third caption with a legibility scrim ----
const Caption: React.FC<{
  f: number;
  dur: number;
  eyebrow: string;
  eyebrowColor?: string;
  title: React.ReactNode;
  stat?: React.ReactNode;
}> = ({ f, dur, eyebrow, eyebrowColor = ACCENT_SOFT, title, stat }) => {
  const op = interpolate(f, [10, 26, dur - 12, dur], [0, 1, 1, 0], clamp);
  const x = interpolate(f, [10, 28], [-26, 0], clamp);
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", opacity: op }}>
      <div
        style={{
          background: "linear-gradient(transparent, rgba(6,8,13,0.92) 68%)",
          padding: "150px 110px 92px",
        }}
      >
        <div style={{ transform: `translateX(${x}px)`, maxWidth: 1400 }}>
          <div
            style={{
              color: eyebrowColor,
              fontFamily: FONT,
              fontSize: 30,
              fontWeight: 700,
              letterSpacing: 5,
              textTransform: "uppercase",
              marginBottom: 18,
            }}
          >
            {eyebrow}
          </div>
          <div style={{ color: TEXT, fontFamily: FONT, fontSize: 70, fontWeight: 700, letterSpacing: -1.5, lineHeight: 1.08 }}>
            {title}
          </div>
          {stat && (
            <div style={{ marginTop: 26, display: "flex", gap: 16, alignItems: "center" }}>{stat}</div>
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Chip: React.FC<{ f: number; delay?: number; color: string; children: React.ReactNode }> = ({
  f,
  delay = 0,
  color,
  children,
}) => {
  const a = interpolate(f, [delay, delay + 16], [0, 1], clamp);
  return (
    <div
      style={{
        opacity: a,
        transform: `scale(${0.86 + 0.14 * a})`,
        transformOrigin: "left center",
        display: "inline-flex",
        alignItems: "center",
        gap: 12,
        padding: "14px 22px",
        borderRadius: 999,
        border: `1px solid ${color}59`,
        background: `${color}1c`,
        color,
        fontFamily: FONT,
        fontSize: 34,
        fontWeight: 700,
        letterSpacing: -0.3,
      }}
    >
      {children}
    </div>
  );
};

const countUp = (f: number, to: number, dur: number, start = 8) =>
  Math.round(interpolate(f, [start, Math.min(dur - 8, start + 46)], [0, to], clamp)).toLocaleString("en-US");

const Logo: React.FC<{ size?: number }> = ({ size = 92 }) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: size * 0.26,
      background: "linear-gradient(135deg,#6366f1,#34d399)",
      display: "grid",
      placeItems: "center",
    }}
  >
    <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 100 100">
      <rect x="28" y="58" width="12" height="20" rx="4.5" fill="#fff" opacity=".82" />
      <rect x="44" y="46" width="12" height="32" rx="4.5" fill="#fff" opacity=".92" />
      <rect x="60" y="34" width="12" height="44" rx="4.5" fill="#fff" />
      <circle cx="66" cy="25" r="7.5" fill="#fff" />
    </svg>
  </div>
);

// A centered, large-type scene (problem + close) — legible when the hero plays small.
const TextScene: React.FC<{ f: number; dur: number; children: React.ReactNode }> = ({ f, dur, children }) => {
  const op = interpolate(f, [0, 14, dur - 16, dur], [0, 1, 1, 0], clamp);
  const y = interpolate(f, [0, 16], [24, 0], clamp);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", textAlign: "center", padding: 120 }}>
      <div style={{ opacity: op, transform: `translateY(${y}px)` }}>{children}</div>
    </AbsoluteFill>
  );
};

type SceneDef = { dur: number; tint?: string; render: (f: number, dur: number) => React.ReactNode };

const SCENES: SceneDef[] = [
  // 1 — the problem
  {
    dur: 82,
    tint: "rgba(240,132,107,0.14)",
    render: (f) => (
      <TextScene f={f} dur={82}>
        <div style={{ color: RED, fontFamily: FONT, fontSize: 32, fontWeight: 700, letterSpacing: 6, textTransform: "uppercase", marginBottom: 26 }}>
          The back office
        </div>
        <div style={{ color: TEXT, fontFamily: FONT, fontSize: 116, fontWeight: 800, letterSpacing: -3, lineHeight: 1.04 }}>
          Runs on one person&rsquo;s memory.
        </div>
        <div style={{ color: MUTE, fontFamily: FONT, fontSize: 56, fontWeight: 600, marginTop: 28 }}>
          The margin, the materials, the paperwork &mdash; all in one head.
        </div>
      </TextScene>
    ),
  },
  // 2 — the 2D org (your whole company)
  {
    dur: 92,
    render: (f, dur) => (
      <>
        <Screen src="capture/cc-org-2d.png" f={f} dur={dur} from={1.04} to={1.1} panY={-10} />
        <Caption
          f={f}
          dur={dur}
          eyebrow="Your whole company"
          title={<>Every person, department &amp; agent &mdash; mapped.</>}
        />
      </>
    ),
  },
  // 3 — the 3D org sphere (same company, premium 3D)
  {
    dur: 118,
    render: (f, dur) => (
      <>
        <Screen src="capture/cc-org-3d.png" f={f} dur={dur} from={1.0} to={1.07} panY={-16} />
        <Caption
          f={f}
          dur={dur}
          eyebrow="One brain"
          title={<>In 2D &mdash; or premium <span style={{ color: ACCENT }}>3D</span>.</>}
          stat={
            <Chip f={f} delay={28} color={ACCENT}>
              38 people · 7 departments · 6 AI agents
            </Chip>
          }
        />
      </>
    ),
  },
  // 4 — dispatch
  {
    dur: 112,
    render: (f, dur) => (
      <>
        <Screen src="capture/cc-dispatch.png" f={f} dur={dur} from={1.03} to={1.09} panY={-12} />
        <Caption
          f={f}
          dur={dur}
          eyebrow="Dispatch"
          title={<>Routes optimized automatically.</>}
          stat={
            <>
              <Chip f={f} delay={24} color={GREEN}>
                9 min/day saved
              </Chip>
              <Chip f={f} delay={40} color={ACCENT_SOFT}>
                10 of 11 jobs assigned
              </Chip>
            </>
          }
        />
      </>
    ),
  },
  // 5 — financial (the headline number)
  {
    dur: 122,
    render: (f, dur) => (
      <>
        <Screen src="capture/cc-financial.png" f={f} dur={dur} from={1.0} to={1.08} panY={-14} />
        <Caption
          f={f}
          dur={dur}
          eyebrow="Financial"
          title={<>Margin leakage, caught today.</>}
          stat={
            <>
              <Chip f={f} delay={20} color={GREEN}>
                ${countUp(f, 119700, dur, 20)} surfaced
              </Chip>
              <Chip f={f} delay={48} color={MUTE}>
                not at month-end
              </Chip>
            </>
          }
        />
      </>
    ),
  },
  // 6 — booking 24/7
  {
    dur: 106,
    render: (f, dur) => (
      <>
        <Screen src="capture/cc-booking.png" f={f} dur={dur} from={1.03} to={1.09} panY={-12} />
        <Caption
          f={f}
          dur={dur}
          eyebrow="Booking · 24/7"
          title={<>Every call answered &amp; booked.</>}
          stat={
            <Chip f={f} delay={26} color={AMBER}>
              even the 9 p.m. one
            </Chip>
          }
        />
      </>
    ),
  },
  // 7 — the approval gate
  {
    dur: 114,
    tint: "rgba(242,182,90,0.12)",
    render: (f, dur) => (
      <>
        <Screen src="capture/cc-agent-controls.png" f={f} dur={dur} from={1.02} to={1.07} panY={-10} />
        <Caption
          f={f}
          dur={dur}
          eyebrow="You stay in control"
          eyebrowColor={AMBER}
          title={<>Nothing happens without your approval.</>}
          stat={
            <Chip f={f} delay={26} color={AMBER}>
              Off · Approve · Auto — every action audited &amp; reversible
            </Chip>
          }
        />
      </>
    ),
  },
  // 8 — self-learning
  {
    dur: 96,
    tint: "rgba(70,211,182,0.13)",
    render: (f, dur) => (
      <>
        <Screen src="capture/cc-learning.png" f={f} dur={dur} from={1.03} to={1.09} panY={-12} />
        <Caption
          f={f}
          dur={dur}
          eyebrow="Self-learning"
          eyebrowColor={GREEN}
          title={
            <>
              And it gets <span style={{ color: GREEN }}>smarter</span> every week.
            </>
          }
        />
      </>
    ),
  },
  // 9 — life after: the whole company at a glance + the close
  {
    dur: 168,
    tint: "rgba(126,162,255,0.2)",
    render: (f, dur) => {
      const imgOp = interpolate(f, [0, 18, dur - 18, dur], [0, 1, 1, 0], clamp);
      const scale = interpolate(f, [0, dur], [1.12, 1.0], clamp);
      const line1 = interpolate(f, [16, 38], [0, 1], clamp);
      const line2 = interpolate(f, [52, 78], [0, 1], clamp);
      const cta = interpolate(f, [104, 128], [0, 1], clamp);
      return (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
          <AbsoluteFill style={{ opacity: imgOp }}>
            <Img
              src={staticFile("capture/demo-sphere-3d.png")}
              style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${scale})` }}
            />
            <AbsoluteFill style={{ background: "radial-gradient(60% 60% at 50% 46%, transparent, rgba(6,8,13,0.78))" }} />
          </AbsoluteFill>
          <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", textAlign: "center", padding: 110 }}>
            <div style={{ opacity: line1, transform: `translateY(${(1 - line1) * 18}px)`, color: ACCENT_SOFT, fontFamily: FONT, fontSize: 38, fontWeight: 700, letterSpacing: 5, textTransform: "uppercase" }}>
              Your whole company, at a glance
            </div>
            <div style={{ opacity: line2, transform: `translateY(${(1 - line2) * 20}px)`, marginTop: 28, color: TEXT, fontFamily: FONT, fontSize: 96, fontWeight: 800, letterSpacing: -2.5, lineHeight: 1.05 }}>
              40% more efficient &mdash;<br />
              <span style={{ color: GREEN }}>and far less stressed.</span>
            </div>
            <div style={{ opacity: cta, marginTop: 50, display: "inline-flex", alignItems: "center", gap: 22 }}>
              <Logo size={70} />
              <span style={{ color: TEXT, fontFamily: FONT, fontSize: 60, fontWeight: 800, letterSpacing: -1 }}>
                Top Builder AI
              </span>
              <span style={{ color: ACCENT, fontFamily: FONT, fontSize: 44, fontWeight: 700, letterSpacing: 0.5, marginLeft: 8 }}>
                topbuilderai.com
              </span>
            </div>
          </AbsoluteFill>
        </AbsoluteFill>
      );
    },
  },
];

export const HERO_DURS = SCENES.map((s) => s.dur);

export const Hero: React.FC = () => {
  const starts = HERO_DURS.reduce<number[]>((acc, _d, k) => {
    acc.push(k === 0 ? 0 : acc[k - 1] + HERO_DURS[k - 1]);
    return acc;
  }, []);
  return (
    <AbsoluteFill style={{ background: INK }}>
      {SCENES.map((scene, k) => (
        <Sequence key={k} from={starts[k]} durationInFrames={scene.dur}>
          <SceneFrame scene={scene} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

const SceneFrame: React.FC<{ scene: SceneDef }> = ({ scene }) => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Bg tint={scene.tint} />
      {scene.render(f, scene.dur)}
    </AbsoluteFill>
  );
};
