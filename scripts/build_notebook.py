"""Generate notebooks/try_compactbench.ipynb.

Regenerate with:

    python scripts/build_notebook.py

Keeping the notebook source in a Python generator (instead of hand-editing
the JSON) avoids the usual diff-review nightmare on `.ipynb` outputs.
"""

from __future__ import annotations

import json
from pathlib import Path


def md(*lines: str) -> dict[str, object]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in lines[:-1]] + [lines[-1]] if lines else [],
    }


def code(*lines: str) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in lines[:-1]] + [lines[-1]] if lines else [],
    }


CELLS: list[dict[str, object]] = [
    md(
        "# CompactBench — zero-install onramp",
        "",
        "This notebook walks you through **running CompactBench against a real model in your browser**,",
        "with no local setup. It uses Groq's free tier (Llama 3.3 70B) so you don't need a GPU or a",
        "paid API key.",
        "",
        "**What you'll do**",
        "",
        "1. Install `compactbench` with provider SDKs.",
        "2. Paste a Groq API key (free at [console.groq.com](https://console.groq.com/keys)).",
        "3. Inspect a single adversarial conversation the engine generates.",
        "4. Run the `hybrid-ledger` built-in compactor end-to-end and see its score.",
        "5. Compare all four built-in baselines head-to-head.",
        "6. Write and plug in your own compactor.",
        "",
        "Total runtime on Colab: **~2 minutes**.",
        "",
        "Repo: https://github.com/compactbench/compactbench  ·  Docs: https://compactbench.github.io/compactbench/",
    ),
    md(
        "## 0 · Install",
        "",
        "`[providers]` pulls in the `groq`, `google-genai`, and `ollama` SDKs so you can swap providers without reinstalling.",
    ),
    code(
        "!pip install -q 'compactbench[providers]'",
        "",
        "import compactbench",
        "print('compactbench', compactbench.__version__ if hasattr(compactbench, \"__version__\") else '(installed)')",
        "!compactbench --help | head -20",
    ),
    md(
        "## 1 · Paste a Groq API key",
        "",
        "Free tier at <https://console.groq.com/keys> — takes 30 seconds and gives you Llama 3.3 70B.",
        "",
        "The cell below hides your input. Nothing is logged or saved.",
    ),
    code(
        "import os",
        "import getpass",
        "",
        "# Colab users: you can also set this once under the 🔑 Secrets panel with name GROQ_API_KEY.",
        "api_key = None",
        "try:",
        "    from google.colab import userdata  # type: ignore",
        "    api_key = userdata.get('GROQ_API_KEY')",
        "except Exception:",
        "    pass",
        "",
        "if not api_key:",
        "    api_key = getpass.getpass('Groq API key: ')",
        "",
        "os.environ['COMPACTBENCH_GROQ_API_KEY'] = api_key",
        "assert api_key, 'Paste the key before continuing.'",
        "print('Key loaded.')",
    ),
    md(
        "## 2 · Inspect a single benchmark case",
        "",
        "Every CompactBench case is generated *deterministically* from a template + seed.",
        'The `buried_constraint` family buries a critical "never do X" rule in a noisy transcript —',
        "and the model is later asked something that tests whether the rule survived compaction.",
        "",
        "Same template + seed + version → always the same case. Reproducible by construction.",
    ),
    code(
        "!compactbench generate --template buried_constraint_v1 --seed 42 --difficulty medium | head -100",
    ),
    md(
        "## 3 · Run the `hybrid-ledger` built-in compactor",
        "",
        "`hybrid-ledger` is the strongest baseline we ship (structured state + append-only ledger).",
        "",
        "This runs against the public **starter** suite (3 templates x 1 case each = 3 cases), with",
        "**one** drift cycle to keep it fast. Full Elite practice runs are longer.",
    ),
    code(
        "!compactbench run \\",
        "  --method built-in:hybrid-ledger \\",
        "  --suite starter \\",
        "  --provider groq \\",
        "  --model llama-3.3-70b-versatile \\",
        "  --drift-cycles 1 \\",
        "  --case-count 1 \\",
        "  --output hybrid.jsonl",
    ),
    md(
        "## 4 · Read the score",
        "",
        "The scorer reports state-fidelity metrics — not output style. What you want to see high:",
        "",
        "- **Overall** (weighted item mean)",
        "- **Drift resistance** (1.0 means no degradation across cycles)",
        "- **Constraint retention** (forbidden behaviors + locked decisions preserved)",
        "- **Compression ratio** (transcript tokens ÷ artifact tokens)",
        "",
        "And low:",
        "",
        "- **Contradiction rate** (responses that violate a constraint or overridden decision)",
    ),
    code(
        "!compactbench score --results hybrid.jsonl",
    ),
    md(
        "## 5 · Head-to-head: all four baselines",
        "",
        "Four built-ins ship in the box. This loops over each, runs it against the same starter",
        "suite, and collects the scores. Expect `naive-summary` to do worst on constraint retention",
        "and `hybrid-ledger` to do best on state fidelity — that's the shape of the leaderboard.",
        "",
        "Runs ~90 seconds on Groq free tier.",
    ),
    code(
        "import subprocess",
        "",
        "baselines = ['naive-summary', 'structured-state', 'hierarchical-summary', 'hybrid-ledger']",
        "scores: dict[str, str] = {}",
        "",
        "for method in baselines:",
        "    print(f'→ running {method} ...')",
        "    out_path = f'{method}.jsonl'",
        "    subprocess.run(",
        "        [",
        "            'compactbench', 'run',",
        "            '--method', f'built-in:{method}',",
        "            '--suite', 'starter',",
        "            '--provider', 'groq',",
        "            '--model', 'llama-3.3-70b-versatile',",
        "            '--drift-cycles', '1',",
        "            '--case-count', '1',",
        "            '--output', out_path,",
        "        ],",
        "        check=True,",
        "    )",
        "    summary = subprocess.run(",
        "        ['compactbench', 'score', '--results', out_path],",
        "        capture_output=True, text=True, check=True,",
        "    )",
        "    scores[method] = summary.stdout",
        "",
        "print()",
        "print('=' * 60)",
        "for method, report in scores.items():",
        "    print(f'\\n### {method}')",
        "    print(report)",
    ),
    md(
        "## 6 · Write your own compactor",
        "",
        "The whole benchmark exists so you can prove your own method beats these baselines.",
        "",
        "Write one async method: `compact(transcript, config, previous_artifact) -> CompactionArtifact`.",
        "The class gets constructed with a `provider` and `model` — use them for any LLM call you",
        "want to make, or ignore them and do a rule-based transform.",
        "",
        "Here's a toy custom compactor that keeps every turn tagged as a system constraint and",
        "prose-summarises the rest. Contrived, but it works:",
    ),
    code(
        "%%writefile my_compactor.py",
        "from __future__ import annotations",
        "",
        "from typing import Any, ClassVar",
        "",
        "from compactbench.compactors import Compactor",
        "from compactbench.contracts import CompactionArtifact, StructuredState, Transcript",
        "from compactbench.providers import CompletionRequest",
        "",
        "",
        "class KeepConstraintsCompactor(Compactor):",
        "    name: ClassVar[str] = 'keep-constraints'",
        "    version: ClassVar[str] = '0.1.0'",
        "",
        "    async def compact(",
        "        self,",
        "        transcript: Transcript,",
        "        config: dict[str, Any] | None = None,",
        "        previous_artifact: CompactionArtifact | None = None,",
        "    ) -> CompactionArtifact:",
        "        constraints = [t.content for t in transcript.turns if 'constraint' in t.tags]",
        "        rest = [t.content for t in transcript.turns if 'constraint' not in t.tags]",
        "",
        "        if rest:",
        "            rsp = await self.provider.complete(",
        "                CompletionRequest(",
        "                    model=self.model,",
        "                    prompt='Summarise briefly, preserving decisions:\\n\\n' + '\\n'.join(rest),",
        "                )",
        "            )",
        "            prose = rsp.text.strip()",
        "        else:",
        "            prose = ''",
        "",
        "        return CompactionArtifact(",
        "            summaryText=prose,",
        "            structured_state=StructuredState(forbidden_behaviors=constraints[:50]),",
        "            selectedSourceTurnIds=[t.id for t in transcript.turns],",
        "            warnings=[],",
        "            methodMetadata={'method': self.name, 'version': self.version},",
        "        )",
    ),
    code(
        "!compactbench run \\",
        "  --method my_compactor.py:KeepConstraintsCompactor \\",
        "  --suite starter \\",
        "  --provider groq \\",
        "  --model llama-3.3-70b-versatile \\",
        "  --drift-cycles 1 \\",
        "  --case-count 1 \\",
        "  --output my_method.jsonl",
        "",
        "!compactbench score --results my_method.jsonl",
    ),
    md(
        "## 7 · What's next",
        "",
        "- **Develop locally** — `pip install compactbench` on your laptop against Ollama or whatever provider you use.",
        "- **Develop against the Elite practice suite** — 15 harder templates across `buried_constraint`, `decision_override`, `entity_confusion`.",
        "  Run with `--suite elite_practice`.",
        "- **Submit to the leaderboard** — open a PR under `submissions/your-handle/your-method/`. The",
        "  [submitting docs](https://compactbench.github.io/compactbench/submitting/) walk through the full protocol.",
        "- **Wrap a LangChain or LlamaIndex pipeline** — see the",
        "  [integrations page](https://compactbench.github.io/compactbench/integrations/) for drop-in adapters.",
        "",
        "Questions? [GitHub issues](https://github.com/compactbench/compactbench/issues) is the best place to ask.",
    ),
]


NOTEBOOK: dict[str, object] = {
    "cells": CELLS,
    "metadata": {
        "colab": {"provenance": [], "toc_visible": True},
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "notebooks" / "try_compactbench.ipynb"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(NOTEBOOK, indent=1), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
