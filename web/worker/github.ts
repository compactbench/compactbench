// GitHub: sign-in for submitters (OAuth, no scopes) and verification of the
// evaluation workflow's OIDC token for the internal endpoints.

export interface GitHubUser {
  login: string;
  id: number;
}

export function authorizeUrl(clientId: string, redirectUri: string, state: string): string {
  const url = new URL("https://github.com/login/oauth/authorize");
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("state", state);
  // No scopes: public profile only. We never keep the token.
  url.searchParams.set("allow_signup", "true");
  return url.toString();
}

/** Exchange an OAuth code for the user's login and id; the access token is discarded. */
export async function userFromCode(
  code: string,
  clientId: string,
  clientSecret: string,
  fetcher: typeof fetch = fetch,
): Promise<GitHubUser | null> {
  const tokenResponse = await fetcher("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, code }),
  });
  const token = ((await tokenResponse.json()) as { access_token?: string }).access_token;
  if (!token) return null;
  const userResponse = await fetcher("https://api.github.com/user", {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "User-Agent": "compactbench" },
  });
  if (!userResponse.ok) return null;
  const user = (await userResponse.json()) as { login?: unknown; id?: unknown };
  if (typeof user.login !== "string" || typeof user.id !== "number") return null;
  return { login: user.login, id: user.id };
}

const b64urlBytes = (text: string): Uint8Array<ArrayBuffer> => {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4);
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
};

const decodePart = (part: string): Record<string, unknown> =>
  JSON.parse(new TextDecoder().decode(b64urlBytes(part))) as Record<string, unknown>;

/** Verify an RS256 JWT against a JWKS URL; returns the claims or null. */
export async function verifyRs256(
  token: string | null,
  jwksUrl: string,
  fetcher: typeof fetch = fetch,
  now = Date.now() / 1000,
): Promise<Record<string, unknown> | null> {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [rawHeader, rawPayload, rawSignature] = parts as [string, string, string];
  let header: Record<string, unknown>;
  let payload: Record<string, unknown>;
  try {
    header = decodePart(rawHeader);
    payload = decodePart(rawPayload);
  } catch {
    return null;
  }
  if (header.alg !== "RS256") return null;
  const jwks = (await (await fetcher(jwksUrl)).json()) as { keys?: (JsonWebKey & { kid?: string })[] };
  const jwk = (jwks.keys ?? []).find((k) => k.kid === header.kid);
  if (!jwk) return null;
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    b64urlBytes(rawSignature),
    new TextEncoder().encode(`${rawHeader}.${rawPayload}`),
  );
  if (!valid) return null;
  if (typeof payload.exp !== "number" || payload.exp < now) return null;
  if (typeof payload.nbf === "number" && payload.nbf > now + 60) return null;
  return payload;
}

export const ACTIONS_ISSUER = "https://token.actions.githubusercontent.com";

/**
 * True when ``token`` is a GitHub Actions OIDC token from ``repo``'s evaluate
 * workflow on main, minted for ``audience``. That is the only caller allowed to
 * read bundles and report status.
 */
export async function isEvaluationWorkflow(
  token: string | null,
  repo: string,
  audience: string,
  fetcher: typeof fetch = fetch,
  now = Date.now() / 1000,
): Promise<boolean> {
  const claims = await verifyRs256(token, `${ACTIONS_ISSUER}/.well-known/jwks`, fetcher, now);
  if (!claims) return false;
  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  return (
    claims.iss === ACTIONS_ISSUER &&
    aud.includes(audience) &&
    claims.repository === repo &&
    claims.ref === "refs/heads/main" &&
    claims.workflow_ref === `${repo}/.github/workflows/evaluate-submission.yml@refs/heads/main`
  );
}
