import React from "react";
import { Composition } from "remotion";

import { Demo } from "./Demo";
import { HowItWorks } from "./HowItWorks";
import { HowItWorksAuto } from "./HowItWorksAuto";
import { Hero, HERO_DURS } from "./Hero";
import { VO_TIMING } from "./voTiming";

const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
// Total length tracks the voice-driven scene timing (falls back to the original hand-authored lengths).
const DEMO_FRAMES = VO_TIMING ? sum(VO_TIMING.Demo) : 1110;
const HIW_FRAMES = VO_TIMING ? sum(VO_TIMING.HowItWorks) : 1395;
const AUTO_FRAMES = VO_TIMING ? sum(VO_TIMING.Auto) : 1595;

export const RemotionRoot: React.FC = () => (
  <>
    {/* The sizzle (length follows the voiceover) */}
    <Composition id="Demo" component={Demo} durationInFrames={DEMO_FRAMES} fps={30} width={1920} height={1080} />
    {/* The "how it works with ServiceTitan" explainer — read-only / approval path (length follows the voiceover) */}
    <Composition id="HowItWorks" component={HowItWorks} durationInFrames={HIW_FRAMES} fps={30} width={1920} height={1080} />
    {/* The Auto-mode explainer — autonomous execution inside guardrails (length follows the voiceover) */}
    <Composition id="HowItWorksAuto" component={HowItWorksAuto} durationInFrames={AUTO_FRAMES} fps={30} width={1920} height={1080} />
    {/* Compact above-the-fold hero sizzle — muted autoplay loop (no voiceover) */}
    <Composition id="Hero" component={Hero} durationInFrames={HERO_DURS.reduce((a, b) => a + b, 0)} fps={30} width={1920} height={1080} />
  </>
);
