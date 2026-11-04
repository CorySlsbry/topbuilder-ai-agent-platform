// Capability checks that decide whether the 3D sphere is safe to render, or whether we should
// fall back to the proven 2D SVG wheel. Both are SSR-safe (guard on `window`/`document`).

/**
 * True only if a real, hardware-accelerated WebGL context is available.
 *
 * `failIfMajorPerformanceCaveat: true` is the load-bearing flag — without it, a blacklisted GPU
 * still "succeeds" by handing back a software rasterizer, and we'd ship a 2fps 3D scene instead
 * of falling back to 2D.
 */
export function detectWebGL(): boolean {
  if (typeof window === "undefined" || typeof document === "undefined") return false;
  if (!("WebGLRenderingContext" in window)) return false;
  try {
    const canvas = document.createElement("canvas");
    const attrs: WebGLContextAttributes = { failIfMajorPerformanceCaveat: true };
    const gl =
      canvas.getContext("webgl2", attrs) ||
      canvas.getContext("webgl", attrs) ||
      canvas.getContext("experimental-webgl", attrs);
    return Boolean(gl);
  } catch {
    return false;
  }
}

/** True when the user has asked the OS to minimize animation. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
