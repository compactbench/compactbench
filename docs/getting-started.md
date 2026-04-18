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

| Provider | Env var | Free tier |
|---|---|---|
| Groq | `COMPACTBENCH_GROQ_API_KEY` | yes |
| Google AI Studio | `COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY` | yes |
| Ollama (local) | `COMPACTBENCH_OLLAMA_BASE_URL` | local only |
| Mock (tests) | (no config needed) | n/a |

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
