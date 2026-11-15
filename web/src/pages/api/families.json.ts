import type { APIRoute } from "astro";
import { families } from "../../lib/data";

export const GET: APIRoute = () =>
  new Response(JSON.stringify({ families }), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
