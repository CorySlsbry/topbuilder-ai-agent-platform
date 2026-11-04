/** @type {import('next').NextConfig} */

// Defense-in-depth headers for the operator dashboard. frame-ancestors 'none' + X-Frame-Options
// stop clickjacking of the gated approve/execute/2FA controls; the CSP is a backstop if any XSS is
// ever introduced. connect-src allows the API origin (overridable via NEXT_PUBLIC_API_BASE_URL) and
// Supabase Auth; 'unsafe-inline'/'unsafe-eval' are required by Next's runtime and echarts.
const API_ORIGIN = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");
const connectSrc = ["'self'", "https://*.supabase.co", API_ORIGIN].filter(Boolean).join(" ");

const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "media-src 'self'",
  "font-src 'self' data:",
  `connect-src ${connectSrc}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "geolocation=(), camera=(), microphone=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const nextConfig = {
  reactStrictMode: true,
  output: "standalone", // small, self-contained server image for Cloud Run
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

module.exports = nextConfig;
