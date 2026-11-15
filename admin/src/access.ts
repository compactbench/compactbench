// Verify a Cloudflare Access JWT (Cf-Access-Jwt-Assertion) with WebCrypto.
// Access already blocks everyone but the owner at the edge; checking the token here
// too means a misconfigured Access policy can't expose the dashboard.

export interface AccessConfig {
  teamDomain: string; // e.g. "compactbench.cloudflareaccess.com"
  audience: string; // the Access application's AUD tag
  ownerEmail: string;
}

interface Jwk extends JsonWebKey {
  kid?: string;
}

const b64url = (text: string): Uint8Array<ArrayBuffer> => {
  const pad = text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4);
  const raw = atob(pad);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

const decodeJson = (part: string): Record<string, unknown> =>
  JSON.parse(new TextDecoder().decode(b64url(part))) as Record<string, unknown>;

/** The verified owner email, or null when the token is missing, invalid or not the owner's. */
export async function verifyAccess(
  token: string | null,
  config: AccessConfig,
  fetcher: typeof fetch = fetch,
  now: number = Date.now() / 1000,
): Promise<string | null> {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [rawHeader, rawPayload, rawSignature] = parts as [string, string, string];
  let header: Record<string, unknown>;
  let payload: Record<string, unknown>;
  try {
    header = decodeJson(rawHeader);
    payload = decodeJson(rawPayload);
  } catch {
    return null;
  }
  if (header.alg !== "RS256") return null;

  const certs = (await (await fetcher(`https://${config.teamDomain}/cdn-cgi/access/certs`)).json()) as {
    keys?: Jwk[];
  };
  const jwk = (certs.keys ?? []).find((k) => k.kid === header.kid);
  if (!jwk) return null;
  const key = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    b64url(rawSignature),
    new TextEncoder().encode(`${rawHeader}.${rawPayload}`),
  );
  if (!valid) return null;

  const aud = payload.aud;
  const audiences = Array.isArray(aud) ? aud : [aud];
  if (!audiences.includes(config.audience)) return null;
  if (payload.iss !== `https://${config.teamDomain}`) return null;
  if (typeof payload.exp !== "number" || payload.exp < now) return null;
  const email = typeof payload.email === "string" ? payload.email.toLowerCase() : "";
  return email && email === config.ownerEmail.toLowerCase() ? email : null;
}
