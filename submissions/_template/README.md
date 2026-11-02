# Method template

A working starting point for a ranked submission.

- `method.py` — a complete compactor (a running summary) that runs as is. Rename the
  class and `name`, then replace the body of `compact` with your method.
- `requirements.txt` — extra dependencies, pinned (`name==version`). Leave it empty if
  you need nothing beyond `compactbench[providers]`.

Test against the public `practice` suite (commands are at the top of `method.py`).
Ranked submissions are paused while the v2 evaluation pipeline is finished. See
[Writing a compactor](../../docs/writing-a-compactor.md) and
[Submitting](../../docs/submitting.md).
