# Leaderboard

Live rankings of compaction methods, segmented by benchmark version and target model. Submitted via PR; evaluated on GitHub Actions; ranked by `elite_score`. See [methodology](methodology.md) for how scores are computed.

<div id="leaderboard-status" style="margin: 1rem 0; color: var(--md-default-fg-color--light);"></div>
<div id="leaderboard-root"></div>

<style>
.cb-table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.9rem; }
.cb-table th, .cb-table td { padding: 0.45rem 0.65rem; border-bottom: 1px solid var(--md-default-fg-color--lightest); text-align: left; }
.cb-table th { background: var(--md-default-bg-color--light, #f0f0f0); font-weight: 600; cursor: pointer; }
.cb-table td.num, .cb-table th.num { text-align: right; font-variant-numeric: tabular-nums; }
.cb-group-header { margin-top: 2rem; font-size: 1.1rem; font-weight: 600; }
.cb-empty { padding: 1rem; background: var(--md-default-bg-color--light, #f7f7f7); border-radius: 4px; }
</style>

<script>
(async function () {
  const statusEl = document.getElementById("leaderboard-status");
  const rootEl = document.getElementById("leaderboard-root");

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  }
  function fmt(n, digits) { return (typeof n === "number") ? n.toFixed(digits) : "—"; }

  try {
    const resp = await fetch("./data/leaderboard.json", {cache: "no-store"});
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    const updated = new Date(data.updated_at);
    statusEl.textContent = `Updated ${updated.toISOString().replace("T", " ").replace(/\..*$/, "")} UTC  ·  ${data.entries.length} entries`;

    if (!data.entries.length) {
      rootEl.innerHTML = `<div class="cb-empty">
        No ranked submissions yet. The first compaction methods will appear here once
        <a href="https://github.com/compactbench/compactbench/issues/6">#6 (Elite templates)</a>
        and the first community submissions land.
        <br><br>
        Want to be first? See <a href="./submitting/">submitting a method</a>.
      </div>`;
      return;
    }

    // Group by (benchmark_version, target_model).
    const groups = new Map();
    for (const row of data.entries) {
      const key = `${row.benchmark_version} · ${row.target_provider}/${row.target_model}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }

    const html = [];
    for (const [groupKey, rows] of groups) {
      html.push(`<div class="cb-group-header">${escapeHtml(groupKey)}</div>`);
      html.push(`<table class="cb-table">
        <thead><tr>
          <th class="num">Rank</th>
          <th>Method</th>
          <th>Submitter</th>
          <th>Tier</th>
          <th class="num">Elite</th>
          <th class="num">Overall</th>
          <th class="num">Drift</th>
          <th class="num">Constraint</th>
          <th class="num">Contradiction</th>
          <th class="num">Compression</th>
        </tr></thead>
        <tbody>
          ${rows.map(r => `<tr>
            <td class="num">${r.rank ?? "—"}</td>
            <td>${escapeHtml(r.method_name)} <small>(${escapeHtml(r.method_version)})</small></td>
            <td>${r.handle ? `@${escapeHtml(r.handle)}` : "—"}${r.org ? ` · ${escapeHtml(r.org)}` : ""}</td>
            <td>${escapeHtml(r.tier)}</td>
            <td class="num">${fmt(r.elite_score, 3)}</td>
            <td class="num">${fmt(r.overall_score, 3)}</td>
            <td class="num">${fmt(r.drift_resistance, 3)}</td>
            <td class="num">${fmt(r.constraint_retention, 3)}</td>
            <td class="num">${fmt(r.contradiction_rate, 3)}</td>
            <td class="num">${fmt(r.compression_ratio, 2)}×</td>
          </tr>`).join("")}
        </tbody>
      </table>`);
    }
    rootEl.innerHTML = html.join("");
  } catch (err) {
    rootEl.innerHTML = `<div class="cb-empty">Could not load leaderboard: ${escapeHtml(err.message)}</div>`;
  }
})();
</script>

## How to get on the board

1. Write a compactor subclassing `compactbench.compactors.Compactor` — see [writing a compactor](writing-a-compactor.md).
2. Run it locally against the `elite_practice` suite until you're happy.
3. Open a PR to [`submissions/`](https://github.com/compactbench/compactbench/tree/main/submissions) — full protocol in [submitting](submitting.md).
4. A maintainer applies the `evaluate` label after code review; GitHub Actions runs your method against the hidden ranked set and posts the score.
5. If you qualify, your entry lands here on merge.

## Tracking

- Submission workflow + leaderboard site: [#5](https://github.com/compactbench/compactbench/issues/5)
- Launch Elite templates: [#6](https://github.com/compactbench/compactbench/issues/6)
- PyPI release + docs polish: [#7](https://github.com/compactbench/compactbench/issues/7)
