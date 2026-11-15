// node --test worker/*.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { secured } from "./security.ts";

test("generated responses get every security header and a deny-all CSP", () => {
  const r = secured(Response.json({ ok: true }, { status: 201 }));
  assert.equal(r.status, 201);
  assert.equal(r.headers.get("X-Content-Type-Options"), "nosniff");
  assert.equal(r.headers.get("X-Frame-Options"), "DENY");
  assert.match(r.headers.get("Strict-Transport-Security") ?? "", /max-age=31536000/);
  assert.equal(r.headers.get("Cross-Origin-Opener-Policy"), "same-origin");
  assert.equal(r.headers.get("Content-Security-Policy"), "default-src 'none'; frame-ancestors 'none'");
});

test("headers a response already sets win, and cookies and redirects survive", async () => {
  const headers = new Headers({ Location: "https://github.com/login", "Content-Security-Policy": "default-src 'self'" });
  headers.append("Set-Cookie", "a=1; Path=/");
  headers.append("Set-Cookie", "b=2; Path=/");
  const r = secured(new Response(null, { status: 302, headers }));
  assert.equal(r.status, 302);
  assert.equal(r.headers.get("Location"), "https://github.com/login");
  assert.equal(r.headers.get("Content-Security-Policy"), "default-src 'self'");
  assert.deepEqual(r.headers.getSetCookie(), ["a=1; Path=/", "b=2; Path=/"]);
});

test("assets keep their own CSP: none is added to them", () => {
  const r = secured(new Response("<html>", { headers: { "Content-Type": "text/html" } }), false);
  assert.equal(r.headers.get("Content-Security-Policy"), null);
  assert.equal(r.headers.get("X-Content-Type-Options"), "nosniff");
});
