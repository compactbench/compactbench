import type { APIRoute } from "astro";
import leaderboard from "../../generated/leaderboard.json";

// The public leaderboard, as JSON. Same rows the leaderboard page renders.
export const GET: APIRoute = () =>
  new Response(JSON.stringify(leaderboard), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
