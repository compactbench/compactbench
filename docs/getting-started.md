# Getting started

!!! tip "Zero-install Colab notebook"
    Want to try CompactBench in your browser without any setup? Open
    [`notebooks/try_compactbench.ipynb`](https://colab.research.google.com/github/compactbench/compactbench/blob/main/notebooks/try_compactbench.ipynb)
    in Colab — it walks through installation, runs the four built-in baselines against a real
    model on Groq's free tier, and ends with writing your own compactor. Under two minutes end-to-end.

## Install

```bash
pip install compactbench
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv pip install compactbench
```

Verify:

```bash
compactbench --version
```

## Configure a provider

CompactBench needs a model provider to evaluate compacted context. Any of the following work out of the box:

| Provider | `--provider` key | Env var | Free tier |
|---|---|---|---|
| Groq | `groq` | `COMPACTBENCH_GROQ_API_KEY` | yes — ~100k tokens/day on Llama 3.3 70B free tier, [upgrade](https://console.groq.com/settings/billing) for higher limits |
| Google AI Studio | `google-ai-studio` | `COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY` | yes — free on Gemini 2.0 Flash, RPM limits apply |
| Anthropic | `anthropic` | `COMPACTBENCH_ANTHROPIC_API_KEY` | credit-based — $5 starter credit with a new account |
| OpenAI | `openai` | `COMPACTBENCH_OPENAI_API_KEY` | credit-based — usage-priced, no true free tier |
| Ollama (local) | `ollama` | `COMPACTBENCH_OLLAMA_BASE_URL` | local only — constrained by your machine |
| Mock (tests) | `mock` | (no config needed) | n/a — returns canned "hello" responses; scores are non-interpretable but the full pipeline runs, useful for CI + pipeline smokes |

!!! tip "Running the full Elite practice suite"
    15 templates × default 5 cases × 2 drift cycles × ~3 eval items per cycle = ~450 LLM calls, which exceeds Groq's free-tier daily token limit. For real evaluation runs use **Anthropic**, **OpenAI**, or a paid **Groq** account. The benchmark auto-detects daily-quota 429s and surfaces them immediately (it will not retry futilely).

Put keys in `.env` at the project root, or export them in your shell.

## Run your first benchmark

Against a local Ollama model:

```bash
compactbench run \
  --method built-in:hybrid-ledger \
  --suite starter \
  --provider ollama \
  --model llama3.2
```

Against Groq:

```bash
compactbench run \
  --method built-in:structured-state \
  --suite starter \
  --provider groq \
  --model llama-3.3-70b-versatile
```

Against Anthropic Claude:

```bash
compactbench run \
  --method built-in:hybrid-ledger \
  --suite starter \
  --provider anthropic \
  --model claude-3-5-haiku-latest
```

Against OpenAI:

```bash
compactbench run \
  --method built-in:hybrid-ledger \
  --suite starter \
  --provider openai \
  --model gpt-4o-mini
```

Results are written to `results.jsonl` by default. Use `--output` to change the path.

## Inspect a single generated case

```bash
compactbench generate --template buried_constraint_v1 --seed 42
```

Same template + seed always produces the same case, so this is useful for debugging your compactor against a specific failure.

## Score results

```bash
compactbench score --results results.jsonl
```

Prints a per-case breakdown plus run-level overall score, drift resistance, constraint retention, contradiction rate, and compression ratio.

## Next steps

- [Write your own compactor](writing-a-compactor.md)
- [Submit to the leaderboard](submitting.md)
