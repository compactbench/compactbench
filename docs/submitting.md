# Submitting to the leaderboard

!!! note "Opening soon"
    Ranked submissions open with the launch of compactbench.com. Everything below describes
    how it will work; until then, develop against the public `practice` suite and check
    your runs with `compactbench qualify`.

Ranked scores come from a **hidden Elite set** that is generated fresh for every ranked
run, at the same difficulty as the public `practice` suite: mixed sessions in private
worlds. There is nothing fixed to memorize, and what you see in your own provider logs
can't be reused on the next run.

## 1. Build and test locally

A method is a Python class that subclasses `compactbench.compactors.Compactor` — see
[Writing a compactor](writing-a-compactor.md). Develop against the public `practice` suite
with any model you like: a hosted one, a local one through Ollama, or your own
OpenAI-compatible server.

```bash
compactbench run --method method.py:MyCompactor --suite practice --cases 4 \
                 --provider openrouter --model qwen/qwen3-235b \
                 --reader-provider anthropic --reader-model claude-haiku-5-5 \
                 --reader-effort high --controls --output results.jsonl
compactbench qualify --results results.jsonl
```

`qualify` applies the same floors the leaderboard does and lists every reason a run would
be rejected.

## 2. Submit on the website

Go to [compactbench.com/submit](https://compactbench.com/submit), sign in with GitHub, and
fill in:

- **Your method:** `method.py`, the class name, a name and version, and any extra
  dependencies, pinned (`name==version`).
- **The model it calls:** any of Anthropic, OpenAI, OpenRouter (hundreds of models), Google
  Gemini, Groq, DeepSeek, Mistral, Together, Fireworks or xAI — or **your own
  OpenAI-compatible endpoint**, with an optional display name for your model. Hosted models
  are shown by their model id; a custom endpoint's display name is shown with a
  "custom endpoint" label and your handle.
- **Your API keys:** a key for that provider, and an Anthropic key that pays for grading
  (about $0.50 a run). If your method runs on Anthropic, one key covers both.

Everything else — suite, difficulty, compactions, cases, token budget, and the reader model
and its effort — is pinned by the season.

**No method of your own? Benchmark a model.** Choose *A reference method on my model*
instead of uploading code, pick one of the published built-ins (`sectioned-summary`,
`hierarchical-summary`, `naive-summary` or `structured-state`), and give the model and keys
as above. The built-in runs unchanged with its default settings, so rows differ only in the
model; they appear on the leaderboard's **By model** board, ranked against other models on
the same method, and are published under
`submissions/<your-handle>/<method>--<provider>--<model>/`. This is how a lab or a provider
can put a number for its model on the board, paid for by its own keys.

**About your keys.** Create dedicated keys with spend limits, and revoke them after your
run. A key is sent once over HTTPS and sealed immediately to the season's public key; only
the evaluation's model proxy (for your method's key) and grader (for the reader key) can
open it. Your method never sees a key.

## 3. Watch it run

You get a status link. A run takes about an hour:

1. **Build.** Your method and its dependencies are built into a container image. Installing
   dependencies happens at build time, with network access but without any secret.
2. **Run.** The container runs under gVisor with **no network except a model proxy**, a
   read-only filesystem, no privileges and resource limits. It receives one compaction
   request at a time — the new turns and its own previous artifact, nothing else. The hidden
   generator, the questions, the reader and the other cases stay outside it.
3. **Proxy.** The proxy is the only thing holding your key. It forwards your method's calls
   only to your provider (or the one endpoint you declared), only for the model you named,
   without streaming, and stops at a token cap. Requests that would have the provider reach
   the internet for your method — server-side tools like web search or fetch, MCP servers,
   images or documents given by URL — are refused; client-side tools (function calling) are
   fine. It logs call metadata only, never request or response bodies.
4. **Publish.** When the run qualifies, it goes straight onto the leaderboard: your method's
   source, its public settings and its scores are published under
   `submissions/<your-handle>/<method>/`. Full traces — including the hidden cases — are
   sealed to the maintainers' key and kept private; the public row carries a SHA-256
   commitment to them, so any score can be audited later.

## Limits

To keep runs fair and the queue moving: one run in progress per account, at most two ranked
runs per account per week, and a daily cap across everyone. Resubmitting a method replaces
its leaderboard row.

## Rules

- Don't submit a method that has seen hidden content, or that was tuned on hidden results.
- A method must not try to reach anything other than its model through the proxy, or to
  detect or fingerprint ranked cases. Attempts are grounds for removal.
- Your method's source is published with its results — that is the audit trail.
- See the [submission terms](submission-terms.md) for what you agree to by submitting.
