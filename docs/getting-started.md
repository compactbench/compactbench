# Getting started

!!! tip "Zero-install Colab notebook"
    Want to try CompactBench in your browser without any setup? Open
    [`notebooks/try_compactbench.ipynb`](https://colab.research.google.com/github/compactbench/compactbench/blob/main/notebooks/try_compactbench.ipynb)
    in Colab — it installs the package, runs the built-in methods and controls on Groq's
    free tier, and ends with writing your own compactor.

## Install

```bash
pip install 'compactbench[providers]'
```

Or with [uv](https://github.com/astral-sh/uv): `uv pip install 'compactbench[providers]'`.
The `providers` extra installs every provider SDK; without it only the offline `mock`
provider works.

```bash
compactbench --version
compactbench suites list
compactbench families list
```

## Two models: the method's and the reader's

A run involves two models, which can be the same:

- **the method's model** (`--provider` / `--model`) — what your compactor calls, if it calls anything;
- **the reader** (`--reader-provider` / `--reader-model`, defaulting to the method's) — the
  model that answers the questions from the compacted artifact.

Hold the reader fixed when comparing methods. Ranked seasons pin it.

## Configure a provider

| Provider | `--provider` key | Env var |
|---|---|---|
| Anthropic | `anthropic` | `COMPACTBENCH_ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `COMPACTBENCH_OPENAI_API_KEY` |
| OpenAI-compatible (vLLM, llama.cpp, LM Studio, OpenRouter, …) | `openai` | `COMPACTBENCH_OPENAI_BASE_URL` (+ key if the server checks one) |
| Groq | `groq` | `COMPACTBENCH_GROQ_API_KEY` |
| Google AI Studio | `google-ai-studio` | `COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY` |
| Ollama (local) | `ollama` | `COMPACTBENCH_OLLAMA_BASE_URL` (default `http://localhost:11434`) |
| Mock (tests) | `mock` | none — canned responses, scores are meaningless |

Put keys in a `.env` file at the project root (only `COMPACTBENCH_*` names are read) or
export them. A real environment variable wins over `.env`.

!!! info "Custom endpoints are recorded"
    Runs against a custom base URL are recorded as `endpoint_kind: "custom"` (the URL itself
    is never stored). Leaderboards segment on it, so a self-hosted model is never ranked
    against the hosted model whose name it was run under.

## Run your first benchmark

```bash
compactbench run --method built-in:hybrid-ledger --suite starter \
                 --provider anthropic --model claude-haiku-5-5 --controls
```

Locally with Ollama:

```bash
compactbench run --method built-in:hybrid-ledger --suite starter \
                 --provider ollama --model qwen2.5:7b-instruct --controls
```

Results go to `results.jsonl` (change with `--output`). Useful options:

| Option | What it does |
|---|---|
| `--suite starter\|practice` | `starter` is a quick smoke test; `practice` matches the ranked Elite difficulty |
| `--cases N` | cases per family (default: the suite's) |
| `--drift-cycles N`, `--difficulty easy\|medium\|hard\|elite` | override the suite's profile |
| `--budget N` | token budget for each artifact (default 2048; `0` disables) |
| `--controls` | also score from the full conversation (ceiling) and from nothing (floor) |
| `--traces FILE` | keep every artifact, question and raw reader reply |
| `--estimate` | print projected calls, tokens and cost; makes no API calls |
| `--resume` | skip cases already in `--output` |

Always run `--estimate` before a large run.

## Read a case

```bash
compactbench generate --family entity_confusion --seed 42 --difficulty easy --text
```

The same family, seed and difficulty always produce the same case, so this is the way to
debug a method against one specific failure.

## Read the scores

```bash
compactbench score --results results.jsonl
```

Shows the family-balanced score with its 95% interval, the score at every cycle, drift
resistance, stale-answer and hallucination rates, and breakdowns by family and by probe
category. With `--controls`, each family also shows its oracle and null scores and the
normalized score between them.

```bash
compactbench qualify --results results.jsonl
```

Runs the leaderboard's qualification floors locally and lists every reason a run would
be rejected.

## Next steps

- [Write your own compactor](writing-a-compactor.md)
- [Methodology](methodology.md)
- [Submitting](submitting.md)
