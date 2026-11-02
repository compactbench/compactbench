# Leaderboard

Rankings of compaction methods on benchmark v2 (scorer 3.0.0). Rows only compete within one
suite, reader model and token budget. **Score** is the family-balanced mean probe score with
its 95% interval; reference rows — maintainer baselines and the oracle / null controls — are
shown for context and never ranked. See the [methodology](methodology.md) for every column.

<div id="leaderboard-status" style="margin: 1rem 0; color: var(--md-default-fg-color--light);"></div>
<div id="leaderboard-root"></div>

<style>
.cb-table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.85rem; }
.cb-table th, .cb-table td { padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--md-default-fg-color--lightest); text-align: left; }
.cb-table th { font-weight: 600; }
.cb-table td.num, .cb-table th.num { text-align: right; font-variant-numeric: tabular-nums; }
.cb-group-header { margin-top: 2rem; font-size: 1.05rem; font-weight: 600; }
.cb-empty { padding: 1rem; background: var(--md-default-bg-color--light, #f7f7f7); border-radius: 4px; }
.cb-tag { font-size: 0.7rem; padding: 0.05rem 0.35rem; border-radius: 3px; border: 1px solid var(--md-default-fg-color--lighter); }
.cb-control td, .cb-baseline td { color: var(--md-default-fg-color--light); }
</style>

<script>
(async function () {
  const statusEl = document.getElementById("leaderboard-status");
  const rootEl = document.getElementById("leaderboard-root");
  const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const fmt = (n, d) => (typeof n === "number") ? n.toFixed(d) : "—";
  const pct = n => (typeof n === "number") ? (100 * n).toFixed(1) + "%" : "—";

  try {
    const resp = await fetch("../data/leaderboard.json", {cache: "no-store"});
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    statusEl.textContent = `Updated ${new Date(data.updated_at).toISOString().replace("T", " ").replace(/\..*$/, "")} UTC · ${data.entries.length} rows`;

    if (!data.entries.length) {
      rootEl.innerHTML = `<div class="cb-empty"><strong>No v2 rows yet.</strong><br><br>
        Benchmark v2 replaced the scorer, so earlier results are not comparable and have been
        retired (they remain in <code>docs/data/archive/</code>). Baseline and control rows
        appear here once they are run on v2; ranked submissions open when the v2 evaluation
        pipeline ships. Until then, develop against <code>--suite practice</code> and check
        your run with <code>compactbench qualify</code>.</div>`;
      return;
    }

    const groups = new Map();
    for (const row of data.entries) {
      const key = `${row.suite} · reader ${row.reader_provider}/${row.reader_model} · ${row.tier} (${row.budget_tokens ?? "no"} tokens)`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }

    const html = [];
    for (const [groupKey, rows] of groups) {
      html.push(`<div class="cb-group-header">${esc(groupKey)}</div>`);
      html.push(`<table class="cb-table"><thead><tr>
          <th class="num">Rank</th><th>Method</th><th>Method model</th><th>By</th>
          <th class="num">Score</th><th class="num">95% CI</th><th class="num">Normalized</th>
          <th class="num">Drift</th><th class="num">Stale</th><th class="num">Hallucination</th>
          <th class="num">Artifact tokens</th>
        </tr></thead><tbody>
        ${rows.map(r => `<tr class="cb-${esc(r.row_kind)}">
          <td class="num">${r.rank ?? "—"}</td>
          <td>${esc(r.method_name)} <small>${esc(r.method_version)}</small>${r.row_kind !== "submission" ? ` <span class="cb-tag">${esc(r.row_kind)}</span>` : ""}</td>
          <td>${esc(r.compactor_provider)}/${esc(r.compactor_model)}${r.compactor_endpoint_kind === "custom" ? " <small>(custom endpoint)</small>" : ""}</td>
          <td>${r.handle ? "@" + esc(r.handle) : ""}${r.org ? (r.handle ? " · " : "") + esc(r.org) : ""}</td>
          <td class="num"><strong>${fmt(r.score, 3)}</strong></td>
          <td class="num">${fmt(r.score_ci_low, 3)}–${fmt(r.score_ci_high, 3)}</td>
          <td class="num">${fmt(r.normalized_score, 3)}</td>
          <td class="num">${fmt(r.drift_resistance, 3)}</td>
          <td class="num">${pct(r.stale_rate)}</td>
          <td class="num">${pct(r.hallucination_rate)}</td>
          <td class="num">${fmt(r.mean_artifact_tokens, 0)}</td>
        </tr>`).join("")}
      </tbody></table>`);
    }
    rootEl.innerHTML = html.join("");
  } catch (err) {
    rootEl.innerHTML = `<div class="cb-empty">Could not load leaderboard: ${esc(err.message)}</div>`;
  }
})();
</script>

## How to get on the board

1. Write a compactor — see [writing a compactor](writing-a-compactor.md).
2. Develop against the public `practice` suite with `--controls`, and check your run with
   `compactbench qualify --results results.jsonl`.
3. Submit — see [submitting](submitting.md).
