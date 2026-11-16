// Security headers for responses the Worker generates. Cloudflare applies public/_headers
// only to static assets, so sign-in, submissions and MCP responses get theirs here.

const COMMON: Record<string, string> = {
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Cross-Origin-Opener-Policy": "same-origin",
};

/** Nothing a JSON or redirect response sends should load or embed anything. */
const LOCKED_DOWN = "default-src 'none'; frame-ancestors 'none'";

/**
 * ``response`` with the security headers it is missing. Headers it already sets win.
 * ``generated`` responses (not static assets) also get a deny-all Content-Security-Policy.
 */
export function secured(response: Response, generated = true): Response {
  const out = new Response(response.body, response);
  for (const [name, value] of Object.entries(COMMON)) {
    if (!out.headers.has(name)) out.headers.set(name, value);
  }
  if (generated && !out.headers.has("Content-Security-Policy")) {
    out.headers.set("Content-Security-Policy", LOCKED_DOWN);
  }
  return out;
}
