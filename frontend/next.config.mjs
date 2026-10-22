// Plain JavaScript (not .ts) so the production image can load it without TypeScript installed.
// The browser talks only to Next; /api is proxied to FastAPI so session cookies stay same-origin.
const backend = process.env.NOEFFORTS_BACKEND_URL ?? "http://127.0.0.1:8000";

/** @type {import("next").NextConfig} */
const nextConfig = {
  // The development server's request log prints raw paths and query strings, which can hold a
  // posting's question key (an answer's URL); it is off. `next start` has no request log.
  logging: { incomingRequests: false },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
