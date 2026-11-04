// Capture real Top Builder AI platform screens from the LIVE deployed app for the hero video.
// Writes crisp PNGs to video/public/capture/. Run from the video/ dir:
//   node scripts/capture_demo.mjs            (headless + SwiftShader WebGL)
//   HEADED=1 node scripts/capture_demo.mjs   (real window — use if a 3D sphere comes out blank)
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const BASE =
  process.env.BASE ||
  "https://topbuilder-ai-agent-web-840472456279.us-central1.run.app";
const OUT = path.resolve("public", "capture");
const HEADED = !!process.env.HEADED;

const browser = await chromium.launch({
  headless: !HEADED,
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    "--hide-scrollbars",
    "--force-color-profile=srgb",
  ],
});
const ctx = await browser.newContext({
  viewport: { width: 1600, height: 900 },
  deviceScaleFactor: 2,
  colorScheme: "dark",
});
const page = await ctx.newPage();
await mkdir(OUT, { recursive: true });

const shot = async (name) => {
  await page.screenshot({ path: path.join(OUT, name + ".png") });
  console.log("  shot:", name);
};
const clickNav = async (label) =>
  page.getByText(label, { exact: true }).first().click();

// 1) Public 280-person 3D org sphere (client-side fixture, no auth).
try {
  console.log("[1] /demo 3D sphere");
  await page.goto(BASE + "/demo", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("canvas", { timeout: 30000 });
  await page.waitForTimeout(6500); // let the sphere render + settle
  await shot("demo-sphere-3d");
} catch (e) {
  console.log("  FAIL demo sphere:", e.message);
}

// 2) Authenticated Command Center via the one-click demo tenant (no password).
try {
  console.log("[2] login -> command center");
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  await page.getByText("Canyon Ridge Mechanical").first().click();
  await page.waitForTimeout(4500);
} catch (e) {
  console.log("  FAIL login:", e.message);
}

// 3) Organization view — capture BOTH Sphere 3D and Classic 2D.
try {
  console.log("[3] Organization 3D + 2D");
  await clickNav("Organization");
  await page.waitForTimeout(2500);
  await page
    .getByRole("button", { name: "Sphere 3D" })
    .click()
    .catch(() => console.log("  (Sphere 3D toggle not clickable / already 3D)"));
  await page.waitForTimeout(5500);
  await shot("cc-org-3d");
  await page
    .getByRole("button", { name: "Classic 2D" })
    .click()
    .catch(() => console.log("  (Classic 2D toggle not found)"));
  await page.waitForTimeout(2800);
  await shot("cc-org-2d");
} catch (e) {
  console.log("  FAIL org:", e.message);
}

// 4) The rest of the Command Center — one screen per "how it works" beat.
const navShot = async (label, name) => {
  try {
    await clickNav(label);
    await page.waitForTimeout(1500);
    // wait for any "Loading…" spinner to clear before shooting (up to 14s)
    await page
      .waitForFunction(() => !/Loading/i.test(document.body.innerText), { timeout: 14000 })
      .catch(() => console.log("  (still loading after 14s)"));
    await page.waitForTimeout(3000); // count-up + chart settle
    await shot(name);
  } catch (e) {
    console.log("  FAIL nav", label + ":", e.message);
  }
};
console.log("[4] Command Center views");
await navShot("Dispatch", "cc-dispatch");
await navShot("Front Desk", "cc-front-desk");
await navShot("Financial", "cc-financial");
await navShot("Inventory", "cc-inventory");
await navShot("Booking", "cc-booking");
await navShot("Agent Controls", "cc-agent-controls");
await navShot("Learning", "cc-learning");
await navShot("Executive", "cc-executive");

await browser.close();
console.log("DONE capture");
