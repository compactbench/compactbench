import type { APIRoute } from "astro";
import { season } from "../../lib/data";

export const GET: APIRoute = () =>
  new Response(JSON.stringify(season), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
