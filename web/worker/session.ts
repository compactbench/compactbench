// Signed cookies: a payload plus an HMAC-SHA256 tag, with an expiry. Used for the
// submitter's GitHub session (handle and id only) and the OAuth state check.

const enc = new TextEncoder();

const b64url = (bytes: Uint8Array): string =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

const unb64url = (text: string): Uint8Array<ArrayBuffer> => {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4);
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
};

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
    "verify",
  ]);
}

export async function signValue(secret: string, payload: Record<string, unknown>, ttlSeconds: number, now = Date.now()): Promise<string> {
  const body = b64url(enc.encode(JSON.stringify({ ...payload, exp: Math.floor(now / 1000) + ttlSeconds })));
  const tag = new Uint8Array(await crypto.subtle.sign("HMAC", await hmacKey(secret), enc.encode(body)));
  return `${body}.${b64url(tag)}`;
}

export async function verifyValue<T extends Record<string, unknown>>(
  secret: string,
  value: string | null | undefined,
  now = Date.now(),
): Promise<T | null> {
  if (!value) return null;
  const [body, tag] = value.split(".");
  if (!body || !tag) return null;
  let ok = false;
  try {
    ok = await crypto.subtle.verify("HMAC", await hmacKey(secret), unb64url(tag), enc.encode(body));
  } catch {
    return null;
  }
  if (!ok) return null;
  try {
    const payload = JSON.parse(new TextDecoder().decode(unb64url(body))) as T & { exp?: number };
    if (typeof payload.exp !== "number" || payload.exp < Math.floor(now / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}

export function readCookie(request: Request, name: string): string | null {
  const header = request.headers.get("Cookie") ?? "";
  for (const part of header.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return rest.join("=");
  }
  return null;
}

export function cookie(name: string, value: string, maxAge: number): string {
  return `${name}=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}
