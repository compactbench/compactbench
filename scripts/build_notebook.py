"""Generate notebooks/try_compactbench.ipynb.

Regenerate with:

    python scripts/build_notebook.py

Keeping the notebook source in a Python generator (instead of hand-editing
the JSON) avoids the usual diff-review nightmare on `.ipynb` outputs.
"""

from __future__ import annotations

import json
import subprocess
import sys
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
        "!compactbench --help | head -20",
    ),
    md(
        "## 1 · Paste a Groq API key",
        "",
        "Free tier at <https://console.groq.com/keys> — takes 30 seconds and gives you open models like gpt-oss-20b.",
        "",
        "The cell below hides your input. Nothing is logged or saved.",
    ),
    code(
        "import getpass",
        "import os",
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
        "Every CompactBench case is generated *deterministically* from a family + seed + difficulty.",
        "The `buried_constraint` family states rules once, buries them among look-alike rules for",
        "other projects, then changes them in later cycles. After each compaction a reader model",
        "answers structured questions using only the compacted artifact.",
        "",
        "Same family + seed + difficulty → always the same case. Reproducible by construction.",
    ),
    code(
        "!compactbench generate --family buried_constraint --seed 42 --difficulty easy --text | head -120",
    ),
    md(
        "## 3 · Run the `hybrid-ledger` built-in compactor",
        "",
        "`hybrid-ledger` is the strongest baseline we ship (structured state + append-only ledger).",
        "",
        "This runs against the public **starter** suite (4 families x 1 case each, ~1.5k-token",
        "conversations) with **one** drift cycle to keep it fast. The `practice` suite is the",
        "difficulty-matched twin of the ranked Elite set: ~32k-token openings and 4 drift cycles.",
    ),
    code(
        "!compactbench run \\",
        "  --method built-in:hybrid-ledger \\",
        "  --suite starter \\",
        "  --provider groq \\",
        "  --model openai/gpt-oss-20b \\",
        "  --drift-cycles 1 \\",
        "  --cases 1 \\",
        "  --output hybrid.jsonl",
    ),
    md(
        "## 4 · Read the score",
        "",
        "Every answer is checked mechanically (option letters, exact values) — no LLM judge.",
        "What you want to see high:",
        "",
        "- **Score** — mean probe score, balanced across families, with a 95% confidence interval",
        "- **Drift resistance** — how much of what was right after the first compaction is still right after the last",
        "",
        "And low:",
        "",
        "- **Stale-answer rate** — picked a decision or value that had since been replaced",
        "- **Hallucination rate** — invented an answer for something that was never decided",
    ),
    code(
        "!compactbench score --results hybrid.jsonl",
    ),
    md(
        "## 5 · Head-to-head: the baselines and the controls",
        "",
        "Four built-in methods plus two controls: `oracle` (keeps everything — the ceiling) and",
        "`null` (keeps nothing — the floor). A method's score only means something between those two.",
        "",
        "Runs ~90 seconds on Groq free tier.",
    ),
    code(
        "import subprocess",
        "",
        "baselines = ['naive-summary', 'structured-state', 'hierarchical-summary', 'hybrid-ledger', 'oracle', 'null']",
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
        "            '--model', 'openai/gpt-oss-20b',",
        "            '--drift-cycles', '1',",
        "            '--cases', '1',",
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
        "Write one async method: `compact(request) -> CompactionArtifact`. At cycle 0",
        "`request.turns` is the whole conversation; after that `request.previous_artifact` is what",
        "you returned last time and `request.turns` holds only what happened since — the earlier",
        "turns are gone, exactly as in a real agent. Stay under `request.token_budget` tokens.",
        "",
        "Here's a toy method: a running summary plus a verbatim ledger of any line that sounds like",
        "a rule or a decision. Contrived, but it works:",
    ),
    code(
        "%%writefile my_compactor.py",
        "from __future__ import annotations",
        "",
        "import re",
        "from typing import ClassVar",
        "",
        "from compactbench.compactors import Compactor",
        "from compactbench.contracts import CompactionArtifact, CompactionRequest, StructuredState",
        "from compactbench.providers import CompletionRequest",
        "from compactbench.rendering import render_request",
        "",
        "RULE_WORDS = re.compile(r'\\b(never|must|always|decision|decided|instead of|owns|taken over)\\b', re.I)",
        "",
        "",
        "class RuleLedgerCompactor(Compactor):",
        "    name: ClassVar[str] = 'rule-ledger'",
        "    version: ClassVar[str] = '0.1.0'",
        "",
        "    async def compact(self, request: CompactionRequest) -> CompactionArtifact:",
        "        previous = request.previous_artifact",
        "        ledger = list(previous.structured_state.locked_decisions) if previous else []",
        "        for turn in request.turns:",
        "            for sentence in re.split(r'(?<=[.!?])\\s+', turn.content):",
        "                if RULE_WORDS.search(sentence) and len(sentence) <= 300:",
        "                    ledger.append(sentence.strip())",
        "        rsp = await self.provider.complete(",
        "            CompletionRequest(",
        "                model=self.model,",
        "                prompt='Update this running summary in under 150 words:\\n\\n' + render_request(request),",
        "            )",
        "        )",
        "        return CompactionArtifact(",
        "            summaryText=rsp.text.strip(),",
        "            structured_state=StructuredState(locked_decisions=ledger[-60:]),",
        "            selectedSourceTurnIds=[t.id for t in request.turns],",
        "            methodMetadata={'method': self.name, 'version': self.version},",
        "        )",
    ),
    code(
        "!compactbench run \\",
        "  --method my_compactor.py:RuleLedgerCompactor \\",
        "  --suite starter \\",
        "  --provider groq \\",
        "  --model openai/gpt-oss-20b \\",
        "  --drift-cycles 1 \\",
        "  --cases 1 \\",
        "  --output my_method.jsonl",
        "",
        "!compactbench score --results my_method.jsonl",
    ),
    md(
        "## 7 · What's next",
        "",
        "- **Develop locally** — `pip install compactbench` on your laptop against Ollama or whatever provider you use.",
        "- **Develop against the practice suite** — the public twin of the ranked Elite set, at the same difficulty.",
        "  Run with `--suite practice --controls` to see your method between the oracle and null controls.",
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
    # Let ruff normalise the code cells (quote style, trailing commas) so CI's
    # format check stays green without having to hand-police strings here.
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        print("formatted via ruff")
    else:
        # Not fatal — maybe ruff isn't installed in this env. The CI lint job
        # will still catch any residual drift.
        print(f"ruff format skipped: {result.stderr.strip() or 'ruff not available'}")


if __name__ == "__main__":
    main()
