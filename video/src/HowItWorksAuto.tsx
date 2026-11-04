import React from "react";
import { AbsoluteFill, interpolate, Sequence, useCurrentFrame } from "remotion";

import { VO_TIMING } from "./voTiming";

// Brand world — identical to HowItWorks.tsx / the sizzle.
const INK = "#0a0b0f";
const PANEL = "#12141b";
const ACCENT = "#7ea2ff";
const ACCENT_SOFT = "#a9c0ff";
const GREEN = "#46d3b6";
const AMBER = "#f2b65a";
const RED = "#f2606a";
const TEXT = "#f4f6fb";
const MUTE = "#8b94a7";
const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, system-ui, sans-serif";
const MONO = "'SF Mono', 'Cascadia Code', Consolas, ui-monospace, monospace";

const i = (f: number, inp: number[], out: number[]): number =>
  interpolate(f, inp, out, { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

const Bg: React.FC = () => (
  <AbsoluteFill
    style={{ background: `radial-gradient(1300px 760px at 50% 16%, rgba(126,162,255,0.16), transparent 62%), ${INK}` }}
  />
);

const Scene: React.FC<{ dur: number; children: (f: number) => React.ReactNode }> = ({ dur, children }) => {
  const f = useCurrentFrame();
  const opacity = i(f, [0, 20, dur - 24, dur], [0, 1, 1, 0]);
  return <AbsoluteFill style={{ opacity }}>{children(f)}</AbsoluteFill>;
};

const Eyebrow: React.FC<{ children: React.ReactNode; color?: string; style?: React.CSSProperties }> = ({
  children,
  color = ACCENT_SOFT,
  style,
}) => (
  <div style={{ color, fontFamily: FONT, fontSize: 26, fontWeight: 600, letterSpacing: 6, textTransform: "uppercase", ...style }}>
    {children}
  </div>
);

const Caption: React.FC<{ children: React.ReactNode; o?: number }> = ({ children, o = 1 }) => (
  <div
    style={{
      position: "absolute",
      bottom: 70,
      left: 0,
      right: 0,
      textAlign: "center",
      color: MUTE,
      fontFamily: FONT,
      fontSize: 32,
      fontWeight: 500,
      opacity: o,
      padding: "0 200px",
    }}
  >
    {children}
  </div>
);

const Wordmark: React.FC<{ style?: React.CSSProperties; size?: number }> = ({ style, size = 34 }) => (
  <div style={{ display: "inline-flex", alignItems: "center", gap: 14, ...style }}>
    <div
      style={{
        width: size + 12,
        height: size + 12,
        borderRadius: 12,
        background: "rgba(126,162,255,0.15)",
        border: "1px solid rgba(126,162,255,0.4)",
        display: "grid",
        placeItems: "center",
        color: ACCENT,
        fontSize: size - 4,
      }}
    >
      ✦
    </div>
    <span style={{ color: TEXT, fontFamily: FONT, fontSize: size, fontWeight: 800, letterSpacing: -1 }}>Top Builder AI</span>
  </div>
);

const Token: React.FC<{ x: number; y: number; color: string; size?: number; o?: number }> = ({ x, y, color, size = 22, o = 1 }) => (
  <div
    style={{
      position: "absolute",
      left: x - size / 2,
      top: y - size / 2,
      width: size,
      height: size,
      borderRadius: "50%",
      background: color,
      boxShadow: `0 0 22px ${color}`,
      opacity: o,
    }}
  />
);

const Vault: React.FC<{ x: number; y: number; w: number; h: number; pulse?: number; label?: boolean }> = ({
  x,
  y,
  w,
  h,
  pulse = 0,
  label = true,
}) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: w,
      height: h,
      borderRadius: 22,
      background: PANEL,
      border: `1px solid rgba(126,162,255,${0.35 + pulse * 0.5})`,
      boxShadow: pulse ? `0 0 ${40 * pulse}px rgba(70,211,182,${0.35 * pulse})` : "none",
      padding: 22,
    }}
  >
    {label && (
      <>
        <div style={{ color: TEXT, fontFamily: FONT, fontSize: 24, fontWeight: 700, opacity: 0.9 }}>ServiceTitan</div>
        <div style={{ color: MUTE, fontFamily: FONT, fontSize: 15, letterSpacing: 3, marginTop: 2 }}>SYSTEM OF RECORD</div>
        {["Jobs", "Customers", "Schedule", "Estimates", "Invoices", "Documents"].map((t) => (
          <div key={t} style={{ color: MUTE, fontFamily: MONO, fontSize: 16, marginTop: 9, opacity: 0.7 }}>
            {t}
          </div>
        ))}
      </>
    )}
  </div>
);

const Chip: React.FC<{ children: React.ReactNode; color: string; x: number; y: number; o?: number }> = ({ children, color, x, y, o = 1 }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      opacity: o,
      padding: "9px 16px",
      borderRadius: 10,
      border: `1px solid ${color}66`,
      background: `${color}1f`,
      color,
      fontFamily: FONT,
      fontSize: 20,
      fontWeight: 700,
      whiteSpace: "nowrap",
    }}
  >
    {children}
  </div>
);

const usd = (n: number) => "$" + Math.round(n).toLocaleString("en-US");

const AGENT = { x: 810, y: 230, w: 300, h: 120 };
const VAULT = { x: 760, y: 690, w: 400, h: 320 };
const GATE_Y = 560;

const AgentNode: React.FC<{ label: string; sub?: string }> = ({ label, sub }) => (
  <div style={{ position: "absolute", left: AGENT.x, top: AGENT.y, width: AGENT.w, height: AGENT.h, borderRadius: 18, background: PANEL, border: `1px solid ${GREEN}55`, padding: 18 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{ width: 12, height: 12, borderRadius: "50%", background: GREEN, boxShadow: `0 0 12px ${GREEN}` }} />
      <span style={{ color: TEXT, fontFamily: FONT, fontSize: 24, fontWeight: 700 }}>{label}</span>
    </div>
    {sub && <div style={{ color: MUTE, fontFamily: MONO, fontSize: 16, marginTop: 12 }}>{sub}</div>}
  </div>
);

// ----------------------------------------------------------------------------------------------
// Scenes — the AUTONOMOUS arc: it reads, decides, and ACTS on its own, inside guardrails you set.
// ----------------------------------------------------------------------------------------------

// A1 — The 2:14 AM call (nobody's awake; the agents are)
const A1: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const tx = i(f, [25, 70], [260, 900]);
      const hitWeb = f > 66;
      const inQueue = i(f, [78, 100], [0, 130]);
      return (
        <>
          <Wordmark style={{ position: "absolute", left: 90, top: 80 }} />
          <Eyebrow style={{ position: "absolute", left: 150, top: 132 }} color={GREEN}>Autonomous mode</Eyebrow>
          <div style={{ position: "absolute", left: 0, right: 0, top: 300, textAlign: "center", color: MUTE, fontFamily: MONO, fontSize: 64, fontWeight: 700, opacity: i(f, [10, 30], [0, 1]) }}>
            2:14 AM
          </div>
          <div style={{ position: "absolute", left: 900, top: 430, width: 4, height: 150, background: hitWeb ? GREEN : ACCENT, opacity: 0.8, borderRadius: 3 }} />
          <Chip color={GREEN} x={830} y={400} o={hitWeb ? i(f, [66, 78], [0, 1]) : 0}>signature-verified webhook ✓</Chip>
          <div style={{ position: "absolute", left: 1010, top: 470, color: MUTE, fontFamily: FONT, fontSize: 18, letterSpacing: 3 }}>EVENT QUEUE</div>
          {[0, 1, 2].map((s) => (
            <div key={s} style={{ position: "absolute", left: 1010, top: 500 + s * 40, width: 220, height: 30, borderRadius: 8, border: "1px solid rgba(255,255,255,0.08)" }} />
          ))}
          <Token x={f < 78 ? tx : 1015 + 110} y={f < 78 ? 505 : 515 + inQueue} color={AMBER} size={26} />
          <div style={{ position: "absolute", left: tx - 110, top: 540, color: AMBER, fontFamily: FONT, fontSize: 20, fontWeight: 600, opacity: i(f, [25, 40, 64, 72], [0, 1, 1, 0]) }}>
            Inbound call — after hours
          </div>
          <Caption o={i(f, [80, 100], [0, 1])}>Nobody's in the office at 2 AM. In <b style={{ color: GREEN }}>Auto</b>, the agents are already working.</Caption>
        </>
      );
    }}
  </Scene>
);

// A2 — Autonomy set to AUTO (the defining difference vs the read-only film)
const A2: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const reveal = i(f, [8, 26], [0, 1]);
      const glow = 0.45 + 0.4 * Math.sin((f / 24) * Math.PI); // steady live pulse on the AUTO segment
      const seg = (label: string, on: boolean, tag?: string) => (
        <div
          style={{
            padding: "16px 36px",
            borderRadius: 12,
            background: on ? `${GREEN}22` : "transparent",
            border: `1px solid ${on ? GREEN : "rgba(255,255,255,0.12)"}`,
            color: on ? GREEN : MUTE,
            fontFamily: FONT,
            fontSize: 28,
            fontWeight: 700,
            opacity: on ? 1 : 0.5,
            position: "relative",
            boxShadow: on ? `0 0 ${30 * glow}px ${GREEN}66` : "none",
          }}
        >
          {label}
          {tag && (
            <span style={{ position: "absolute", top: -15, right: 10, fontSize: 13, letterSpacing: 2, color: on ? GREEN : MUTE }}>{tag}</span>
          )}
        </div>
      );
      return (
        <>
          <Eyebrow style={{ position: "absolute", left: 0, right: 0, top: 250, textAlign: "center" }} color={GREEN}>Per-agent autonomy</Eyebrow>
          <div style={{ position: "absolute", left: 0, right: 0, top: 350, display: "flex", gap: 14, justifyContent: "center", opacity: reveal }}>
            {seg("Off", false)}
            {seg("Approve", false)}
            {seg("Auto", true, "SELECTED")}
          </div>
          <div style={{ position: "absolute", left: 0, right: 0, top: 490, textAlign: "center", color: TEXT, fontFamily: FONT, fontSize: 36, fontWeight: 600, opacity: i(f, [26, 44], [0, 1]) }}>
            It acts on its own — <span style={{ color: GREEN }}>no approval needed</span>.
          </div>
          <div style={{ position: "absolute", left: 0, right: 0, top: 548, textAlign: "center", color: MUTE, fontFamily: FONT, fontSize: 24, opacity: i(f, [40, 58], [0, 1]) }}>
            You choose which agents — and exactly what they're allowed to do.
          </div>
          <Caption o={i(f, [52, 70], [0, 1])}>Flip an agent to <b style={{ color: GREEN }}>Auto</b>, and it runs the work without waiting on you.</Caption>
        </>
      );
    }}
  </Scene>
);

// A3 — READ + DECIDE (it still reads ServiceTitan, then decides)
const A3: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const ty = i(f, [22, 58], [VAULT.y, AGENT.y + AGENT.h]);
      return (
        <>
          <Vault {...VAULT} />
          <AgentNode label="Booking agent" sub="reads: open slots · customer · history" />
          <svg style={{ position: "absolute", inset: 0 }} width={1920} height={1080}>
            <path d={`M 960 ${AGENT.y + AGENT.h} L 960 ${VAULT.y}`} stroke={ACCENT} strokeWidth={2} strokeDasharray="6 10" strokeDashoffset={-f * 2} opacity={i(f, [10, 30], [0, 0.6])} fill="none" />
          </svg>
          <Token x={960} y={ty} color={ACCENT} o={f > 18 && f < 66 ? 1 : i(f, [60, 72], [1, 0])} />
          <Chip color={ACCENT} x={1240} y={690} o={i(f, [30, 46], [0, 1])}>reads the live signal</Chip>
          <Chip color={GREEN} x={1240} y={748} o={i(f, [50, 68], [0, 1])}>→ decides: book Thu 9:00a</Chip>
          <Caption o={i(f, [60, 78], [0, 1])}>It <b style={{ color: ACCENT_SOFT }}>reads</b> ServiceTitan and <b style={{ color: GREEN }}>decides</b> what needs to happen.</Caption>
        </>
      );
    }}
  </Scene>
);

// A4 — Deterministic compute vs narration (why auto is safe: the decision is tested code, not a guess)
const A4: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const dollars = Math.round(i(f, [25, 70], [0, 2895]));
      const calls = Math.round(i(f, [30, 70], [0, 8]));
      const filled = f > 96;
      return (
        <>
          <Eyebrow style={{ position: "absolute", left: 0, right: 0, top: 110, textAlign: "center" }}>Deterministic compute · the model only narrates</Eyebrow>
          <div style={{ position: "absolute", left: 360, top: 240, width: 520 }}>
            <div style={{ color: MUTE, fontFamily: FONT, fontSize: 20, letterSpacing: 4 }}>COMPUTE</div>
            <div style={{ marginTop: 26, display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ color: TEXT, fontFamily: FONT, fontSize: 30 }}>After-hours recovered</span>
              <span style={{ color: GREEN, fontFamily: MONO, fontSize: 46, fontWeight: 800 }}>{usd(dollars)}</span>
            </div>
            <div style={{ color: GREEN, fontFamily: MONO, fontSize: 18, opacity: i(f, [70, 80], [0, 1]) }}>✓ tested</div>
            <div style={{ marginTop: 22, display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ color: TEXT, fontFamily: FONT, fontSize: 30 }}>Calls booked</span>
              <span style={{ color: TEXT, fontFamily: MONO, fontSize: 40, fontWeight: 800 }}>{calls} of 14</span>
            </div>
            <div style={{ color: GREEN, fontFamily: MONO, fontSize: 18, opacity: i(f, [74, 84], [0, 1]) }}>✓ tested</div>
          </div>
          <div style={{ position: "absolute", left: 960, top: 230, width: 2, height: 420, background: `linear-gradient(${ACCENT}, transparent)`, opacity: 0.6 }} />
          <div style={{ position: "absolute", left: 1040, top: 240, width: 520 }}>
            <div style={{ color: MUTE, fontFamily: FONT, fontSize: 20, letterSpacing: 4 }}>NARRATES</div>
            <div style={{ marginTop: 26, padding: 22, borderRadius: 16, background: "rgba(169,192,255,0.08)", border: `1px solid ${ACCENT_SOFT}44`, color: ACCENT_SOFT, fontFamily: FONT, fontSize: 28, lineHeight: 1.4 }}>
              “Booked <b style={{ color: filled ? TEXT : MUTE }}>{filled ? "8" : "▯"}</b> jobs you'd have missed overnight — <b style={{ color: filled ? GREEN : MUTE }}>{filled ? "$2,895" : "$▯"}</b> recovered.”
            </div>
          </div>
          {f > 86 && f < 100 && <Token x={i(f, [86, 98], [880, 1090])} y={330} color={GREEN} />}
          <Caption o={i(f, [100, 116], [0, 1])}>Numbers = tested code. Words = model. <b style={{ color: ACCENT_SOFT }}>The model never computes the figure.</b></Caption>
        </>
      );
    }}
  </Scene>
);

// A5 — ACTS automatically: the action flows straight through the OPEN gate and writes back (no tap)
const A5: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const cardY = i(f, [10, 62], [AGENT.y + 30, VAULT.y - 70]); // descends THROUGH the open gate
      const cardO = i(f, [6, 20, 56, 70], [0, 1, 1, 0]); // fades as it enters the vault
      const pulse = i(f, [62, 78, 120], [0, 1, 0.3]);
      const tokenY = i(f, [40, 72], [GATE_Y, VAULT.y + 150]);
      return (
        <>
          <Vault {...VAULT} pulse={pulse} />
          {/* OPEN gate (green) — the difference from the read-only film's amber/closed gate */}
          <div style={{ position: "absolute", left: 560, top: GATE_Y, width: 800, height: 6, borderRadius: 4, background: GREEN, opacity: 0.9, boxShadow: `0 0 20px ${GREEN}` }} />
          <div style={{ position: "absolute", left: 560, top: GATE_Y + 16, color: GREEN, fontFamily: FONT, fontSize: 18, letterSpacing: 3 }}>AUTO · GATE OPEN</div>
          {/* solid live channel through the gate into the vault */}
          <div style={{ position: "absolute", left: 958, top: GATE_Y, width: 4, height: VAULT.y - GATE_Y, background: GREEN, opacity: 0.75 }} />
          {/* draft card descending through the gate */}
          <div style={{ position: "absolute", left: 700, top: cardY, width: 520, borderRadius: 18, background: PANEL, border: `1px solid ${GREEN}66`, padding: 22, opacity: cardO }}>
            <div style={{ display: "inline-flex", padding: "6px 12px", borderRadius: 8, background: `${GREEN}22`, color: GREEN, fontFamily: MONO, fontSize: 20, fontWeight: 700 }}>book_appointment</div>
            {["Customer  ·  Jane Whitfield", "When  ·  Thu 9:00a", "Tech  ·  Marco R.", "Value  ·  $485"].map((r, k) => (
              <div key={r} style={{ marginTop: 12, color: TEXT, fontFamily: FONT, fontSize: 24, opacity: i(f, [12 + k * 3, 20 + k * 3], [0, 1]) }}>{r}</div>
            ))}
          </div>
          {/* write token */}
          {f > 38 && f < 76 && <Token x={960} y={tokenY} color={GREEN} />}
          {/* booked cell appears in the vault */}
          <div style={{ position: "absolute", left: VAULT.x + 22, top: VAULT.y + 140, padding: "8px 14px", borderRadius: 8, background: `${GREEN}22`, border: `1px solid ${GREEN}`, color: GREEN, fontFamily: MONO, fontSize: 20, fontWeight: 700, opacity: i(f, [70, 82], [0, 1]) }}>
            Thu 9:00a — BOOKED ✓
          </div>
          <Chip color={GREEN} x={1250} y={470} o={i(f, [78, 92], [0, 1])}>auto-executed · 1.8s · no tap</Chip>
          <Caption o={i(f, [96, 112], [0, 1])}>In Auto it doesn't wait for a tap — it <b style={{ color: GREEN }}>books the job itself</b>, in seconds.</Caption>
        </>
      );
    }}
  </Scene>
);

// A6 — Every auto action is signed, logged, reversible — undo anything
const A6: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const pulse = i(f, [10, 30, 120], [0.2, 0.55, 0.3]);
      const receipts = ["signed 🔏", "logged 📓", "idempotent", "reversible ↺"];
      const log: [string, string][] = [
        ["12:04:13a", "book_appointment"],
        ["12:04:51a", "assign_tech"],
        ["12:05:30a", "send_confirmation"],
      ];
      return (
        <>
          <Vault {...VAULT} pulse={pulse} />
          {/* audit log card */}
          <div style={{ position: "absolute", left: 300, top: 300, width: 500, borderRadius: 16, background: PANEL, border: "1px solid rgba(255,255,255,0.08)", padding: 24 }}>
            <div style={{ color: MUTE, fontFamily: FONT, fontSize: 16, letterSpacing: 3, marginBottom: 14 }}>AUDIT LOG · AUTO</div>
            {log.map(([t, a], k) => (
              <div key={a} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12, opacity: i(f, [16 + k * 8, 28 + k * 8], [0, 1]) }}>
                <span style={{ color: MUTE, fontFamily: MONO, fontSize: 18 }}>{t}</span>
                <span style={{ color: TEXT, fontFamily: MONO, fontSize: 18 }}>{a}</span>
                <span style={{ color: GREEN, fontFamily: MONO, fontSize: 18 }}>✓</span>
              </div>
            ))}
          </div>
          {/* receipts */}
          <div style={{ position: "absolute", left: 1240, top: 330 }}>
            {receipts.map((r, k) => (
              <div key={r} style={{ color: TEXT, fontFamily: FONT, fontSize: 28, marginBottom: 14, opacity: i(f, [38 + k * 6, 48 + k * 6], [0, 1]) }}>{r}</div>
            ))}
          </div>
          {/* big one-tap undo */}
          <div style={{ position: "absolute", left: 1240, top: 560, display: "inline-flex", padding: "16px 28px", borderRadius: 12, border: `1px solid ${ACCENT}`, background: `${ACCENT}1f`, color: ACCENT, fontFamily: FONT, fontSize: 28, fontWeight: 800, opacity: i(f, [70, 84], [0, 1]) }}>
            ↺ Undo any action — one tap
          </div>
          <Caption o={i(f, [92, 108], [0, 1])}>Every auto action is <b style={{ color: GREEN }}>signed, logged, and reversible</b>. Undo any of it, anytime.</Caption>
        </>
      );
    }}
  </Scene>
);

// A7 — Bounded autonomy: it only acts inside the limits you set, and fails closed
const A7: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const allowed = ["Book appointments", "Assign the right tech", "Send confirmations", "File documents"];
      const asks = ["Refunds", "Price overrides", "Anything over $1,000"];
      const refusing = f > 96 && f < 124;
      return (
        <>
          <Eyebrow style={{ position: "absolute", left: 0, right: 0, top: 120, textAlign: "center" }}>Bounded autonomy · you set the limits</Eyebrow>
          {/* allowed column */}
          <div style={{ position: "absolute", left: 300, top: 240, width: 560, borderRadius: 18, background: PANEL, border: `1px solid ${GREEN}44`, padding: 30 }}>
            <div style={{ color: GREEN, fontFamily: FONT, fontSize: 24, fontWeight: 800, letterSpacing: 1, marginBottom: 16 }}>AUTO IS ALLOWED TO</div>
            {allowed.map((a, k) => (
              <div key={a} style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 16, opacity: i(f, [14 + k * 6, 26 + k * 6], [0, 1]) }}>
                <span style={{ color: GREEN, fontSize: 26 }}>✓</span>
                <span style={{ color: TEXT, fontFamily: FONT, fontSize: 28 }}>{a}</span>
              </div>
            ))}
          </div>
          {/* asks-first column */}
          <div style={{ position: "absolute", left: 1060, top: 240, width: 560, borderRadius: 18, background: PANEL, border: `1px solid ${AMBER}44`, padding: 30 }}>
            <div style={{ color: AMBER, fontFamily: FONT, fontSize: 24, fontWeight: 800, letterSpacing: 1, marginBottom: 16 }}>STILL ASKS YOU FIRST</div>
            {asks.map((a, k) => (
              <div key={a} style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 16, opacity: i(f, [40 + k * 6, 52 + k * 6], [0, 1]) }}>
                <span style={{ color: AMBER, fontSize: 24 }}>🔒</span>
                <span style={{ color: TEXT, fontFamily: FONT, fontSize: 28 }}>{a}</span>
              </div>
            ))}
          </div>
          {/* fail-closed chip */}
          <div style={{ position: "absolute", left: 0, right: 0, top: 700, textAlign: "center" }}>
            <span style={{ display: "inline-flex", padding: "12px 22px", borderRadius: 12, border: `1px solid ${refusing ? RED : GREEN}66`, background: `${refusing ? RED : GREEN}14`, color: refusing ? RED : GREEN, fontFamily: FONT, fontSize: 24, fontWeight: 700, opacity: i(f, [70, 84], [0, 1]) }}>
              {refusing ? "unverified write — REFUSED" : "fails closed · never fabricates a change"}
            </span>
          </div>
          <Caption o={i(f, [104, 120], [0, 1])}>It <b style={{ color: GREEN }}>fails closed</b>, and only acts inside the limits you set — anything bigger still asks first.</Caption>
        </>
      );
    }}
  </Scene>
);

// A8 — The loop, autonomous: six agents running on their own, around the clock
const A8: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const cx = 960;
      const cy = 470;
      const R = 300;
      const agents = ["Booking", "Routing", "Documents", "Workforce", "Financial", "Inventory"];
      const stats = [
        ["$2,895", "after-hours recovered"],
        ["60 min/day", "drive time saved"],
        ["9 of 12", "docs auto-filed"],
        ["24/7", "no one babysitting"],
      ];
      return (
        <>
          <div style={{ position: "absolute", left: cx - 90, top: cy - 60, width: 180, height: 120, borderRadius: 16, background: PANEL, border: `1px solid ${ACCENT}55`, display: "grid", placeItems: "center", textAlign: "center" }}>
            <span style={{ color: TEXT, fontFamily: FONT, fontSize: 22, fontWeight: 700 }}>ServiceTitan</span>
          </div>
          {agents.map((a, k) => {
            const ang = (-90 + k * 60) * (Math.PI / 180);
            const x = cx + R * Math.cos(ang);
            const y = cy + R * Math.sin(ang);
            const ap = i(f, [10 + k * 5, 26 + k * 5], [0, 1]);
            const t = ((f * 1.6 + k * 14) % 60) / 60;
            const rising = t < 0.5;
            const tt = rising ? t * 2 : (t - 0.5) * 2;
            const px = cx + (R * (rising ? 1 - tt : tt)) * Math.cos(ang);
            const py = cy + (R * (rising ? 1 - tt : tt)) * Math.sin(ang);
            return (
              <React.Fragment key={a}>
                <div style={{ position: "absolute", left: x - 80, top: y - 26, width: 160, textAlign: "center", color: TEXT, fontFamily: FONT, fontSize: 22, fontWeight: 700, opacity: ap, padding: "10px 0", borderRadius: 10, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>{a}</div>
                {f > 30 && <Token x={px} y={py} color={rising ? ACCENT : GREEN} size={12} o={ap * 0.9} />}
              </React.Fragment>
            );
          })}
          <div style={{ position: "absolute", left: 0, right: 0, bottom: 120, display: "flex", justifyContent: "center", gap: 40, opacity: i(f, [50, 75], [0, 1]) }}>
            {stats.map(([big, sub]) => (
              <div key={sub} style={{ textAlign: "center" }}>
                <div style={{ color: GREEN, fontFamily: MONO, fontSize: 36, fontWeight: 800 }}>{big}</div>
                <div style={{ color: MUTE, fontFamily: FONT, fontSize: 18 }}>{sub}</div>
              </div>
            ))}
          </div>
          <div style={{ position: "absolute", left: 0, right: 0, top: 70, textAlign: "center", color: GREEN, fontFamily: FONT, fontSize: 24, letterSpacing: 4, textTransform: "uppercase" }}>Six agents · running on their own · around the clock</div>
        </>
      );
    }}
  </Scene>
);

// A9 — Branded Top Builder AI logo outro (identical to the read-only film)
const A9: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const reveal = i(f, [6, 34], [0, 1]);
      const glow = 0.5 + 0.5 * Math.sin((f / dur) * Math.PI);
      const chip = 136;
      return (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", textAlign: "center" }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", transform: `scale(${i(f, [6, 38], [0.92, 1])})` }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 32, opacity: reveal }}>
              <div
                style={{
                  width: chip,
                  height: chip,
                  borderRadius: 34,
                  background: "rgba(126,162,255,0.16)",
                  border: "1px solid rgba(126,162,255,0.45)",
                  display: "grid",
                  placeItems: "center",
                  color: ACCENT,
                  fontSize: chip - 58,
                  boxShadow: `0 0 ${72 * glow}px rgba(126,162,255,${0.42 * glow})`,
                }}
              >
                ✦
              </div>
              <span style={{ color: TEXT, fontFamily: FONT, fontSize: 116, fontWeight: 800, letterSpacing: -2 }}>Top Builder AI</span>
            </div>
            <div
              style={{
                width: i(f, [32, 62], [0, 660]),
                height: 1,
                background: `linear-gradient(90deg, transparent, ${ACCENT}, transparent)`,
                marginTop: 48,
                opacity: 0.85,
              }}
            />
            <div style={{ color: MUTE, fontFamily: FONT, fontSize: 38, fontWeight: 500, marginTop: 36, opacity: i(f, [48, 72], [0, 1]) }}>
              The AI operating layer for ServiceTitan contractors.
            </div>
            <div style={{ color: ACCENT, fontFamily: FONT, fontSize: 52, fontWeight: 800, letterSpacing: 1, marginTop: 30, opacity: i(f, [66, 90], [0, 1]) }}>
              topbuilderai.com
            </div>
          </div>
        </AbsoluteFill>
      );
    }}
  </Scene>
);

export const HowItWorksAuto: React.FC = () => {
  // Scene durations follow the Auto voiceover (generated voTiming); fall back to hand-authored pacing.
  const DEFAULT_DURS = [190, 120, 135, 200, 210, 185, 205, 160, 190];
  const durs = VO_TIMING?.Auto ?? DEFAULT_DURS;
  const starts = durs.reduce<number[]>((acc, _d, k) => {
    acc.push(k === 0 ? 0 : acc[k - 1] + durs[k - 1]);
    return acc;
  }, []);
  const scenes: React.FC<{ dur: number }>[] = [A1, A2, A3, A4, A5, A6, A7, A8, A9];
  return (
    <AbsoluteFill style={{ background: INK }}>
      <Bg />
      {scenes.map((Comp, k) => (
        <Sequence key={k} from={starts[k]} durationInFrames={durs[k]}>
          <Comp dur={durs[k]} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
