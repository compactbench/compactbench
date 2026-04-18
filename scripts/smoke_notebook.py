"""Run the Colab notebook's ``compactbench`` commands against the mock provider.

Lives in CI so any drift in CLI flag names, suite keys, or built-in compactor
keys breaks the build *before* the notebook confuses a Colab user. We re-read
the notebook source each run, so when ``scripts/build_notebook.py`` regenerates
the notebook the smoke test automatically picks up the new commands.

Rewrites every ``--provider <X>`` / ``--model <X>`` pair in the extracted
commands so no API keys are needed. Also honours ``%%writefile`` cell magics
so the "write your own compactor" cell's sibling ``!compactbench run`` command
still has a method file to load.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

NOTEBOOK_PATH = Path(__file__).resolve().parent.parent / "notebooks" / "try_compactbench.ipynb"

_PROVIDER_RE = re.compile(r"(--provider)(\s+|=)(\S+)")
_MODEL_RE = re.compile(r"(--model)(\s+|=)(\S+)")


def _cell_source(cell: dict[str, object]) -> str:
    src = cell.get("source", "")
    if isinstance(src, list):
        return "".join(str(x) for x in src)
    return str(src)


def _rewrite_providers_models(cmd: str) -> str:
    cmd = _PROVIDER_RE.sub(r"\1\2mock", cmd)
    cmd = _MODEL_RE.sub(r"\1\2mock-model", cmd)
    return cmd


def _extract_shell_commands(cell_src: str) -> list[str]:
    """Pick out ``!compactbench ...`` lines, joining backslash-continued ones."""
    commands: list[str] = []
    buf: list[str] = []
    for line in cell_src.splitlines():
        stripped = line.strip()
        if not buf and not stripped.startswith("!"):
            continue
        if buf:
            buf.append(line)
        else:
            buf.append(line)
        if line.rstrip().endswith("\\"):
            continue
        joined = " ".join(b.rstrip(" \\").lstrip().lstrip("!") for b in buf)
        commands.append(joined.strip())
        buf = []
    if buf:
        joined = " ".join(b.rstrip(" \\").lstrip().lstrip("!") for b in buf)
        commands.append(joined.strip())
    return [c for c in commands if c.startswith("compactbench")]


def _handle_writefile(cell_src: str, cwd: Path) -> bool:
    """If the cell is a ``%%writefile`` magic, write the remaining content to disk.

    Returns True if we handled the cell (and no further processing is needed).
    """
    lines = cell_src.splitlines(keepends=True)
    if not lines or not lines[0].strip().startswith("%%writefile"):
        return False
    parts = lines[0].strip().split(None, 1)
    if len(parts) != 2:
        return True
    target = cwd / parts[1].strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(lines[1:]), encoding="utf-8")
    print(f"  wrote {target.relative_to(cwd)}")
    return True


def _extract_subprocess_compactbench(cell_src: str) -> list[list[str]]:
    """Find ``subprocess.run([..., 'compactbench', ...])`` calls and return the arg lists."""
    found: list[list[str]] = []
    # A dumb but effective match for our known pattern.
    for block in re.finditer(r"subprocess\.run\(\s*\[([^\]]+)\]", cell_src):
        args_src = block.group(1)
        # Evaluate the simple list-of-strings literal.
        try:
            args = [
                item.strip().strip("'").strip('"')
                for item in args_src.split(",")
                if item.strip() and not item.strip().startswith("#")
            ]
        except Exception:
            continue
        if not args or args[0] != "compactbench":
            continue
        rewritten: list[str] = []
        i = 0
        while i < len(args):
            if args[i] == "--provider" and i + 1 < len(args):
                rewritten.extend([args[i], "mock"])
                i += 2
            elif args[i] == "--model" and i + 1 < len(args):
                rewritten.extend([args[i], "mock-model"])
                i += 2
            else:
                rewritten.append(args[i])
                i += 1
        found.append(rewritten)
    return found


def main() -> int:
    nb = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    cells = nb.get("cells", [])
    if not isinstance(cells, list):
        print("notebook has no cells array", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        executed = 0
        for i, cell in enumerate(cells):
            if not isinstance(cell, dict) or cell.get("cell_type") != "code":
                continue
            src = _cell_source(cell)

            if _handle_writefile(src, cwd):
                executed += 1
                continue

            shell_commands = _extract_shell_commands(src)
            subprocess_commands = _extract_subprocess_compactbench(src)
            if not shell_commands and not subprocess_commands:
                continue

            for cmd in shell_commands:
                if "--help" in cmd:
                    print(f"[cell {i}] skipping help line: {cmd!r}")
                    continue
                rewritten = _rewrite_providers_models(cmd)
                args = shlex.split(rewritten)
                print(f"[cell {i}] $ {' '.join(args)}")
                result = subprocess.run(
                    args,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    print(result.stdout)
                    print(result.stderr, file=sys.stderr)
                    print(f"[cell {i}] failed with exit {result.returncode}", file=sys.stderr)
                    return 1
                executed += 1

            for args in subprocess_commands:
                print(f"[cell {i}] $ {' '.join(args)}")
                result = subprocess.run(
                    args,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    print(result.stdout)
                    print(result.stderr, file=sys.stderr)
                    print(f"[cell {i}] failed with exit {result.returncode}", file=sys.stderr)
                    return 1
                executed += 1

        if executed == 0:
            print(
                "no compactbench commands found in notebook — smoke test is a no-op",
                file=sys.stderr,
            )
            return 1
        print(f"notebook smoke test OK: ran {executed} commands")
    return 0


if __name__ == "__main__":
    sys.exit(main())
