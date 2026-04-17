# r/LocalLLaMA launch post

## Title

I built a benchmark that measures how well LLM context compaction actually works (open source, hidden ranked set)

## Body

tl;dr: every long-context app has to compact conversation history eventually — summary, structured state, whatever. Nothing really measures how well that compaction holds up. CompactBench does, and it works with Ollama out of the box.

**What it does**

Takes a generated conversation with things the model has to remember ("never do X", "the plan changed to Y", "Alice owns task A, Bob owns task B"). Hands it to your compactor. Replaces the full conversation with whatever the compactor returned. Asks the model questions that require the preserved state to answer correctly. Scores what survived.

Then it does it again, across drift cycles — compact, continue, compact — to see what degrades over multiple passes.

**Why Ollama folks might care**

- The whole thing runs locally against Ollama. No cloud required to develop.
- Your custom local model = your own leaderboard row if you submit.
- The public "practice" suite is in the repo; run it in one command:

```
pip install compactbench
compactbench run --method built-in:hybrid-ledger --suite starter --provider ollama --model llama3.2
compactbench score --results results.jsonl
```

That gives you a baseline against the four built-in compactors — naive summary, structured state, hierarchical summary, hybrid ledger — so you can see where each one wins and loses.

**The hidden ranked set**

The ranked leaderboard uses templates you don't see. Public practice is for development; the hidden ranked content is rotated on version bumps so methods can't just memorize templates. Same pattern as SWE-bench.

**How to submit**

1. Implement a Compactor subclass (one method: `async def compact(transcript, config, previous_artifact)`)
2. Run it locally against the public `elite_practice` suite
3. Open a PR at https://github.com/compactbench/compactbench
4. A maintainer reviews the code and runs it against the hidden set; score lands on the leaderboard

Apache 2.0. Python. Targeting Llama 3.3 70B and Gemini 2.0 Flash on the first leaderboard versions, but adding more models as community submissions come in.

Would love to see what the LocalLLaMA crowd's compaction methods look like — this stuff is where half the "why is my agent broken" bugs live in production, and the usual summarization-style answers aren't great.

Repo: https://github.com/compactbench/compactbench
