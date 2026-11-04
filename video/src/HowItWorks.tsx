import React from "react";
import { AbsoluteFill, interpolate, Sequence, useCurrentFrame } from "remotion";

import { VO_TIMING } from "./voTiming";

// Brand world — identical to the sizzle (Demo.tsx).
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
  // Slower, calmer cross-fades + a hold beat between screens.
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

// The ServiceTitan vault-pillar (system of record) — calm, dim, unchanging.
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

// ----------------------------------------------------------------------------------------------
// Scenes
// ----------------------------------------------------------------------------------------------

// S1 — The 2:14 AM call
const S1: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const tx = i(f, [25, 70], [260, 900]);
      const hitWeb = f > 66;
      const inQueue = i(f, [78, 100], [0, 130]);
      return (
        <>
          <Wordmark style={{ position: "absolute", left: 90, top: 80 }} />
          <Eyebrow style={{ position: "absolute", left: 150, top: 132 }}>The AI operating layer</Eyebrow>
          <div style={{ position: "absolute", left: 0, right: 0, top: 300, textAlign: "center", color: MUTE, fontFamily: MONO, fontSize: 64, fontWeight: 700, opacity: i(f, [10, 30], [0, 1]) }}>
            2:14 AM
          </div>
          {/* webhook bar */}
          <div style={{ position: "absolute", left: 900, top: 430, width: 4, height: 150, background: hitWeb ? GREEN : ACCENT, opacity: 0.8, borderRadius: 3 }} />
          <Chip color={GREEN} x={830} y={400} o={hitWeb ? i(f, [66, 78], [0, 1]) : 0}>signature-verified webhook ✓</Chip>
          {/* event queue */}
          <div style={{ position: "absolute", left: 1010, top: 470, color: MUTE, fontFamily: FONT, fontSize: 18, letterSpacing: 3 }}>EVENT QUEUE</div>
          {[0, 1, 2].map((s) => (
            <div key={s} style={{ position: "absolute", left: 1010, top: 500 + s * 40, width: 220, height: 30, borderRadius: 8, border: "1px solid rgba(255,255,255,0.08)" }} />
          ))}
          {/* token */}
          <Token x={f < 78 ? tx : 1015 + 110} y={f < 78 ? 505 : 515 + inQueue} color={AMBER} size={26} />
          <div style={{ position: "absolute", left: tx - 110, top: 540, color: AMBER, fontFamily: FONT, fontSize: 20, fontWeight: 600, opacity: i(f, [25, 40, 64, 72], [0, 1, 1, 0]) }}>
            Inbound call — after hours
          </div>
          <Caption o={i(f, [80, 100], [0, 1])}>Missed &amp; after-hours calls = lost jobs. The Booking agent drains the queue 24/7.</Caption>
        </>
      );
    }}
  </Scene>
);

// Shared architecture frame: vault low-center, Booking agent node high-center, gate between.
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

// S2 — READ (read-only proof)
const S2: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const ty = i(f, [55, 95], [VAULT.y, AGENT.y + AGENT.h]); // token rises vault->agent
      return (
        <>
          <Vault {...VAULT} />
          <AgentNode label="Booking agent" sub="reads: open slots · customer · schedule" />
          {/* dotted query line down */}
          <svg style={{ position: "absolute", inset: 0 }} width={1920} height={1080}>
            <path d={`M 960 ${AGENT.y + AGENT.h} L 960 ${VAULT.y}`} stroke={ACCENT} strokeWidth={2} strokeDasharray="6 10" strokeDashoffset={-f * 2} opacity={i(f, [10, 30], [0, 0.6])} fill="none" />
          </svg>
          {/* ghost row stays on the vault (read-only proof) */}
          <div style={{ position: "absolute", left: VAULT.x + 22, top: VAULT.y + 150, width: 220, height: 24, borderRadius: 6, background: "rgba(126,162,255,0.10)", border: "1px dashed rgba(126,162,255,0.4)", opacity: i(f, [55, 70], [0, 1]) }} />
          {/* rising cool-blue token */}
          <Token x={960} y={ty} color={ACCENT} o={f > 50 && f < 100 ? 1 : i(f, [95, 105], [1, 0])} />
          <Chip color={GREEN} x={1240} y={700} o={i(f, [96, 112], [0, 1])}>READ-ONLY · nothing changed</Chip>
          <Caption o={i(f, [100, 118], [0, 1])}>It <b style={{ color: ACCENT_SOFT }}>reads</b> ServiceTitan — the agents never silently touch your data.</Caption>
        </>
      );
    }}
  </Scene>
);

// S3 — Deterministic compute vs narration
const S3: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const dollars = Math.round(i(f, [25, 70], [0, 2895]));
      const calls = Math.round(i(f, [30, 70], [0, 8]));
      const filled = f > 96;
      return (
        <>
          <Eyebrow style={{ position: "absolute", left: 0, right: 0, top: 110, textAlign: "center" }}>Deterministic compute · the model only narrates</Eyebrow>
          {/* COMPUTE column */}
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
          {/* hairline wall */}
          <div style={{ position: "absolute", left: 960, top: 230, width: 2, height: 420, background: `linear-gradient(${ACCENT}, transparent)`, opacity: 0.6 }} />
          {/* NARRATES column */}
          <div style={{ position: "absolute", left: 1040, top: 240, width: 520 }}>
            <div style={{ color: MUTE, fontFamily: FONT, fontSize: 20, letterSpacing: 4 }}>NARRATES</div>
            <div style={{ marginTop: 26, padding: 22, borderRadius: 16, background: "rgba(169,192,255,0.08)", border: `1px solid ${ACCENT_SOFT}44`, color: ACCENT_SOFT, fontFamily: FONT, fontSize: 28, lineHeight: 1.4 }}>
              “Booked <b style={{ color: filled ? TEXT : MUTE }}>{filled ? "8" : "▯"}</b> jobs you'd have missed overnight — <b style={{ color: filled ? GREEN : MUTE }}>{filled ? "$2,895" : "$▯"}</b> recovered.”
            </div>
          </div>
          {/* token compute -> bubble */}
          {f > 86 && f < 100 && <Token x={i(f, [86, 98], [880, 1090])} y={i(f, [86, 98], [330, 330])} color={GREEN} />}
          <Caption o={i(f, [100, 116], [0, 1])}>Numbers = tested code. Words = model. <b style={{ color: ACCENT_SOFT }}>The model never computes the figure.</b></Caption>
        </>
      );
    }}
  </Scene>
);

// S4 — PROPOSE (draft halts at the gate)
const S4: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const cardY = i(f, [10, 60], [AGENT.y + 40, GATE_Y - 230]); // descends, halts above the gate
      return (
        <>
          <Vault {...VAULT} />
          {/* approval gate bar (closed) */}
          <div style={{ position: "absolute", left: 560, top: GATE_Y, width: 800, height: 6, borderRadius: 4, background: AMBER, opacity: 0.85, boxShadow: `0 0 18px ${AMBER}88` }} />
          <div style={{ position: "absolute", left: 560, top: GATE_Y + 16, color: AMBER, fontFamily: FONT, fontSize: 18, letterSpacing: 3 }}>APPROVAL GATE</div>
          {/* dashed dead write-channel below gate */}
          <svg style={{ position: "absolute", inset: 0 }} width={1920} height={1080}>
            <path d={`M 960 ${GATE_Y + 8} L 960 ${VAULT.y}`} stroke={AMBER} strokeWidth={2} strokeDasharray="4 12" opacity={0.4} fill="none" />
          </svg>
          <Chip color={AMBER} x={1000} y={620}>🔒 awaiting approval</Chip>
          {/* draft card */}
          <div style={{ position: "absolute", left: 700, top: cardY, width: 520, borderRadius: 18, background: PANEL, border: `1px solid ${ACCENT}66`, padding: 22, transform: `scale(${i(f, [10, 25], [0.9, 1])})` }}>
            <div style={{ display: "inline-flex", padding: "6px 12px", borderRadius: 8, background: "rgba(126,162,255,0.15)", color: ACCENT, fontFamily: MONO, fontSize: 20, fontWeight: 700 }}>book_appointment</div>
            {["Customer  ·  Jane Whitfield", "When  ·  Thu 9:00a", "Tech  ·  Marco R.", "Value  ·  $485"].map((r, k) => (
              <div key={r} style={{ marginTop: 12, color: TEXT, fontFamily: FONT, fontSize: 24, opacity: i(f, [22 + k * 4, 32 + k * 4], [0, 1]) }}>{r}</div>
            ))}
            <div style={{ position: "absolute", right: 0, top: 18, padding: "6px 30px", background: AMBER, color: INK, fontFamily: FONT, fontWeight: 800, fontSize: 18, transform: "rotate(8deg)", opacity: i(f, [30, 42], [0, 1]) }}>DRAFT</div>
          </div>
          <Caption o={i(f, [70, 90], [0, 1])}><b style={{ color: AMBER }}>PROPOSED</b> · external system untouched — nothing written yet.</Caption>
        </>
      );
    }}
  </Scene>
);

// S5 — Autonomy gate: Off / Approve(DEFAULT) / Auto, then the tap
const S5: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const pressed = f > 78;
      const gateColor = pressed ? GREEN : AMBER;
      const cursorX = i(f, [30, 60], [1180, 980]);
      const ripple = i(f, [78, 105], [0, 360]);
      const seg = (label: string, on: boolean, tag?: string, dim?: boolean) => (
        <div style={{ padding: "14px 30px", borderRadius: 12, background: on ? `${(pressed ? GREEN : AMBER)}22` : "transparent", border: `1px solid ${on ? (pressed ? GREEN : AMBER) : "rgba(255,255,255,0.12)"}`, color: on ? (pressed ? GREEN : AMBER) : dim ? MUTE : TEXT, fontFamily: FONT, fontSize: 26, fontWeight: 700, opacity: dim ? 0.5 : 1, position: "relative" }}>
          {label}
          {tag && <span style={{ position: "absolute", top: -14, right: 8, fontSize: 13, letterSpacing: 2, color: on ? gateColor : MUTE }}>{tag}</span>}
        </div>
      );
      return (
        <>
          {/* segmented switch */}
          <div style={{ position: "absolute", left: 0, right: 0, top: 300, display: "flex", gap: 12, justifyContent: "center" }}>
            {seg("Off", false, undefined, true)}
            {seg("Approve", true, "DEFAULT")}
            {seg("Auto", false, "opt-in", true)}
          </div>
          <div style={{ position: "absolute", left: 0, right: 0, top: 230, textAlign: "center", color: MUTE, fontFamily: FONT, fontSize: 26 }}>Default: a human approves.</div>
          {/* the approve button + gate */}
          <div style={{ position: "absolute", left: 810, top: 520, width: 300, padding: "22px 0", textAlign: "center", borderRadius: 14, background: `${gateColor}22`, border: `1px solid ${gateColor}`, color: gateColor, fontFamily: FONT, fontSize: 30, fontWeight: 800, transform: `scale(${pressed ? i(f, [78, 84, 92], [1, 0.94, 1]) : 1})` }}>
            {pressed ? "APPROVED ✓" : "Approve"}
          </div>
          {/* ripple */}
          {pressed && <div style={{ position: "absolute", left: 960 - ripple / 2, top: 565 - ripple / 2, width: ripple, height: ripple, borderRadius: "50%", border: `2px solid ${GREEN}`, opacity: i(f, [78, 105], [0.6, 0]) }} />}
          {/* cursor */}
          {!pressed && <div style={{ position: "absolute", left: cursorX, top: 560, color: TEXT, fontSize: 40 }}>▲</div>}
          <Caption o={i(f, [90, 108], [0, 1])}>You decide each agent's autonomy. The gate opens only when <b style={{ color: GREEN }}>you</b> tap approve.</Caption>
        </>
      );
    }}
  </Scene>
);

// S6 — EXECUTE: write back, signed/logged/reversible + fail-closed beat
const S6: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const ty = i(f, [22, 60], [GATE_Y, VAULT.y + 150]); // green token descends into vault
      const pulse = i(f, [55, 70, 110], [0, 1, 0.3]);
      const receipts = ["signed 🔏", "logged 📓", "idempotent", "reversible ↺"];
      const refusing = f > 92 && f < 116;
      return (
        <>
          <Vault {...VAULT} pulse={pulse} />
          {/* solid live channel */}
          <div style={{ position: "absolute", left: 958, top: GATE_Y, width: 4, height: VAULT.y - GATE_Y, background: GREEN, opacity: 0.8 }} />
          {/* verified guard lights FIRST */}
          <Chip color={GREEN} x={770} y={GATE_Y - 50} o={i(f, [4, 18], [0, 1])}>live integration verified ✓</Chip>
          {/* descending write token */}
          {f > 20 && f < 64 && <Token x={960} y={ty} color={GREEN} />}
          {/* booked cell */}
          <div style={{ position: "absolute", left: VAULT.x + 22, top: VAULT.y + 140, padding: "8px 14px", borderRadius: 8, background: `${GREEN}22`, border: `1px solid ${GREEN}`, color: GREEN, fontFamily: MONO, fontSize: 20, fontWeight: 700, opacity: i(f, [58, 70], [0, 1]) }}>
            Thu 9:00a — BOOKED ✓
          </div>
          {/* receipt strip */}
          <div style={{ position: "absolute", left: 1230, top: 720 }}>
            {receipts.map((r, k) => (
              <div key={r} style={{ color: TEXT, fontFamily: FONT, fontSize: 26, marginBottom: 12, opacity: i(f, [66 + k * 6, 76 + k * 6], [0, 1]) }}>{r}</div>
            ))}
            <div style={{ marginTop: 8, display: "inline-flex", padding: "8px 16px", borderRadius: 10, border: `1px solid ${ACCENT}66`, color: ACCENT, fontFamily: FONT, fontSize: 20, fontWeight: 700, opacity: i(f, [96, 106], [0, 1]) }}>↺ Undo (one-tap)</div>
          </div>
          {/* fail-closed honest beat */}
          <div style={{ position: "absolute", left: 360, top: 470, width: 320, padding: 18, borderRadius: 14, background: refusing ? `${RED}1a` : `${GREEN}14`, border: `1px solid ${refusing ? RED : GREEN}66`, color: refusing ? RED : GREEN, fontFamily: FONT, fontSize: 22, fontWeight: 700, opacity: i(f, [88, 98], [0, 1]) }}>
            {refusing ? "WRITE REFUSED — integration unverified" : "verified ✓"}
          </div>
          <Caption o={i(f, [116, 132], [0, 1])}>It <b style={{ color: GREEN }}>writes back</b> only after approval — and fails closed: it never fabricates a ServiceTitan change.</Caption>
        </>
      );
    }}
  </Scene>
);

// S7 — the loop closes: six agents, one heartbeat
const S7: React.FC<{ dur: number }> = ({ dur }) => (
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
        ["$472.48", "quote on a phone"],
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
            // pulsing dual-current token along the radius
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
          {/* proof stat satellites */}
          <div style={{ position: "absolute", left: 0, right: 0, bottom: 120, display: "flex", justifyContent: "center", gap: 40, opacity: i(f, [50, 75], [0, 1]) }}>
            {stats.map(([big, sub]) => (
              <div key={sub} style={{ textAlign: "center" }}>
                <div style={{ color: GREEN, fontFamily: MONO, fontSize: 36, fontWeight: 800 }}>{big}</div>
                <div style={{ color: MUTE, fontFamily: FONT, fontSize: 18 }}>{sub}</div>
              </div>
            ))}
          </div>
          <div style={{ position: "absolute", left: 0, right: 0, top: 70, textAlign: "center", color: ACCENT_SOFT, fontFamily: FONT, fontSize: 24, letterSpacing: 4, textTransform: "uppercase" }}>Six agents · one loop · signed · logged · reversible</div>
        </>
      );
    }}
  </Scene>
);

// S8 — Payoff line (leads into the logo outro)
const S8: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => (
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", textAlign: "center", padding: 200 }}>
        <div
          style={{
            color: TEXT,
            fontFamily: FONT,
            fontSize: 46,
            fontWeight: 600,
            maxWidth: 1340,
            lineHeight: 1.45,
            opacity: i(f, [0, 30], [0, 1]),
            transform: `translateY(${i(f, [0, 30], [16, 0])}px)`,
          }}
        >
          It reads ServiceTitan, proposes the work, <span style={{ color: ACCENT_SOFT }}>you approve</span>, it writes it back —{" "}
          <span style={{ color: GREEN }}>signed, logged, reversible.</span>
        </div>
      </AbsoluteFill>
    )}
  </Scene>
);

// S9 — Branded Top Builder AI logo outro (the film ends here)
const S9: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    {(f) => {
      const reveal = i(f, [6, 34], [0, 1]);
      const glow = 0.5 + 0.5 * Math.sin((f / dur) * Math.PI); // one gentle breath of glow
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

export const HowItWorks: React.FC = () => {
  // Scene durations follow the voiceover (generated voTiming) so the picture tracks the narration;
  // fall back to the hand-authored pacing when no voiceover timing is present.
  const DEFAULT_DURS = [144, 165, 174, 162, 162, 180, 162, 96, 150];
  const durs = VO_TIMING?.HowItWorks ?? DEFAULT_DURS;
  const starts = durs.reduce<number[]>((acc, _d, k) => {
    acc.push(k === 0 ? 0 : acc[k - 1] + durs[k - 1]);
    return acc;
  }, []);
  const scenes: React.FC<{ dur: number }>[] = [S1, S2, S3, S4, S5, S6, S7, S8, S9];
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
