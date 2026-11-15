// Seal a secret to a season's public key — the same scheme as compactbench.sealing:
// ephemeral X25519, HKDF-SHA256 (info = label | ephemeral | recipient | context),
// AES-256-GCM. The Worker seals a submitter's API key the moment it arrives, so the
// plain key is never stored.

const PREFIX = "cbseal1:";
const INFO = new TextEncoder().encode("compactbench-seal-v1");

const b64url = (bytes: Uint8Array): string =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

const unb64url = (text: string): Uint8Array<ArrayBuffer> => {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4);
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
};

const concat = (...parts: Uint8Array[]): Uint8Array<ArrayBuffer> => {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
};

export async function seal(publicKey: string, plaintext: string, context: string): Promise<string> {
  const recipientRaw = unb64url(publicKey);
  if (recipientRaw.length !== 32) throw new Error("public key must be 32 bytes");
  const recipient = await crypto.subtle.importKey("raw", recipientRaw, { name: "X25519" }, false, []);
  const ephemeral = (await crypto.subtle.generateKey({ name: "X25519" }, true, ["deriveBits"])) as CryptoKeyPair;
  const ephemeralRaw = new Uint8Array(await crypto.subtle.exportKey("raw", ephemeral.publicKey));
  const shared = await crypto.subtle.deriveBits(
    { name: "X25519", public: recipient } as unknown as AlgorithmIdentifier,
    ephemeral.privateKey,
    256,
  );
  const hkdf = await crypto.subtle.importKey("raw", shared, "HKDF", false, ["deriveKey"]);
  const info = concat(INFO, ephemeralRaw, recipientRaw, new TextEncoder().encode(context));
  // An empty salt is the same as RFC 5869's default (HashLen zero bytes) that Python uses.
  const key = await crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0), info },
    hkdf,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt"],
  );
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, new TextEncoder().encode(plaintext)),
  );
  return PREFIX + b64url(concat(ephemeralRaw, nonce, ciphertext));
}
