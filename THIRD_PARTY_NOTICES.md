# Third-party notices

`src/compactbench/compactors/agent_defaults.py` reproduces the default compaction prompts of
two open-source agents, so the benchmark can measure them as shipped. The prompt texts are
copied unchanged from the pinned commits below and remain under their original licenses.

## OpenAI Codex CLI

- Source: <https://github.com/openai/codex>, commit `a394ff9cf66e9c17258077e8f8295178ca0c2025`
- Files: `codex-rs/prompts/templates/compact/prompt.md`,
  `codex-rs/prompts/templates/compact/summary_prefix.md`; behaviour from
  `codex-rs/core/src/compact.rs`
- License: Apache License 2.0 (the same license as CompactBench)

```
OpenAI Codex
Copyright 2025 OpenAI
```

## LangChain

- Source: <https://github.com/langchain-ai/langchain>, commit
  `2529c2d1f2f98c7467e02ade9edcd21c80a9c34e`
- File: `libs/langchain_v1/langchain/agents/middleware/summarization.py`
  (`DEFAULT_SUMMARY_PROMPT` and the middleware's defaults)
- License: MIT

```
MIT License

Copyright (c) LangChain, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
