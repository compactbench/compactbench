---
name: forget-less
description: Writes compaction instructions that keep what matters when an agent's context is compacted (decisions and what they replaced, rules with their scope, names with roles, exact figures, task status), based on CompactBench Season 1 results. Use when the user wants Claude Code or their own agent to forget less after /compact or auto-compaction, asks for "compact instructions" or a better summarization prompt, or reports that instructions, decisions or task state were lost after a compaction.
when_to_use: Also for setting LangChain's SummarizationMiddleware summary_prompt, Codex CLI's compact_prompt, or a LlamaIndex memory summarize_prompt.
---

# Forget less through compaction

When an agent compacts its context it rewrites the conversation as a summary and carries on
from that; whatever the summary drops or gets wrong is gone. CompactBench measured eight ways
of writing that summary on 48 hidden conversations, each compacted five times
(Season 1: Claude Haiku 5.5 writes and reads, 1,024-token summaries, scores 0-100). Use what it
found to write the user's compaction instructions.

## What the results show

1. **Fixed sections beat a free summary.** The same single call scored 51.9 with seven fixed
   headings against 45.1 as a plain summary; names and roles went from 20 to 65.
2. **Replace what changed, and say what it replaced.** A summary rewritten from its previous
   version drifts: the sectioned summary fell from 73 after the first compaction to 39 after
   the fifth and repeated a superseded value 17% of the time. The method told to keep the newer
   version and note what it replaced held at 49-51 with 4%.
3. **Track tasks with their status.** Task state was the hardest family for every summary
   (5-17); the method that kept tasks as explicit records reached 36.
4. **Keep each name with its role.** Explicit entity records scored 81 on names and roles.

Full write-up and data: <https://github.com/compactbench/compactbench/blob/main/docs/forget-less.md>.

## Steps

1. **Find where the instructions go** and read what is there now:

   | Agent | Where |
   |---|---|
   | Claude Code | a `# Compact instructions` section in `CLAUDE.md` at the root of the current project (used on every compaction; ask before creating the file); `/compact <instructions>` for one manual compaction |
   | Codex CLI | `compact_prompt = """..."""` in `~/.codex/config.toml`, or `experimental_compact_prompt_file` |
   | LangChain | `SummarizationMiddleware(..., summary_prompt=...)`; it is a format string, so keep the `{messages}` placeholder and double any other braces |
   | LlamaIndex | `ChatSummaryMemoryBuffer.from_defaults(..., summarize_prompt=...)` (deprecated upstream in favour of `Memory`) |
   | Their own code | the prompt their summarization call sends |

   Stay in the current project; don't search other folders for files. If a section already
   exists, edit it rather than adding a second one.

2. **Start from this text** and keep its structure. Adapt the wording to the project, keep it
   short (the instructions are sent on every compaction), and drop nothing from the last
   paragraph:

   ```text
   When you compact, write the summary you will continue from, in these sections, and keep
   each one current:
   1. Primary request and intent
   2. Decisions and constraints: each rule as it stands now, with its scope and exceptions
   3. People and responsibilities: each name with its role and what they own
   4. Facts and figures: exact numbers, dates, versions and identifiers, copied verbatim
   5. Tasks: each one with its status (done, in progress, pending, blocked) and owner
   6. Open questions
   7. Current state and next step

   When something has changed since the earlier summary, write only the new version and add
   "(replaced: <old version>)". Drop what was cancelled or reverted. Keep rules that are still
   in force, however long ago they were stated.
   ```

   For a coding agent such as Claude Code, it is reasonable to add to section 4 "file paths,
   commands and error messages", to section 5 "mark a task done only once it was verified, for
   example by running the tests", and to section 7 "the branch and the files being edited".
   Tell the user these coding additions were not part of what Season 1 measured.

3. **Show the user the exact text and where it goes** before writing it, then make the edit.

4. **Be honest about the evidence.** Each part comes from a measured method, but this
   combination has not been scored as a whole. If the user wants a number for their own setup,
   use the `measure-compaction` skill to compare it against a baseline on the same cases, with
   their own API keys.

## Don't

- Don't claim the combined prompt "scores" anything; quote only the Season 1 figures above.
- Don't paste the template into a file without the user seeing it, and don't replace an
  existing compaction section the user wrote without saying what changes.
- Don't add instructions that only help a benchmark (for example "anticipate quiz questions").
