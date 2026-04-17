# AI Twitter / X launch thread

4-tweet thread. Replace "@compactbench" if we end up with a different handle.

---

**Tweet 1 (hook)**

Launching CompactBench: an open benchmark for LLM context compaction.

Measures what SWE-bench and MMLU don't — the layer in your app that decides what to keep when the conversation gets long. That's where agents silently lose constraints, decisions, and entity ownership.

🧵

---

**Tweet 2 (what it measures)**

Three v1 failure modes:

• buried constraints ("never do X" deep in noisy context)
• decision overrides (A → B; does the compactor keep B or average?)
• entity confusion (who owns what when multiple people are in play)

Hidden ranked set. Rotated seeds. Multi-cycle drift scoring. Nothing to overfit on.

---

**Tweet 3 (how it works)**

```
pip install compactbench

compactbench run \
  --method built-in:hybrid-ledger \
  --suite starter \
  --provider ollama \
  --model llama3.2

compactbench score --results results.jsonl
```

Works with Groq, Google AI Studio, Ollama out of the box.

---

**Tweet 4 (call to action)**

Apache 2.0. Python. Submit methods via PR — GitHub Actions runs them on a hidden ranked set; score lands on a public leaderboard.

Currently looking for: method submissions, new template families, and anyone who wants to add a provider.

Repo: https://github.com/compactbench/compactbench
Leaderboard: https://compactbench.github.io/compactbench/leaderboard/
