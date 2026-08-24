"""Reject submissions that still contain ``FILL_ME`` placeholders from the template.

Run in CI before the evaluate job to catch copy-paste submissions early and
give the submitter a clear error message instead of a runtime crash.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLACEHOLDER = "FILL_ME"
TEMPLATE_DIR = Path("submissions/_template")


def find_offenders(root: Path) -> list[tuple[Path, int, str]]:
    offenders: list[tuple[Path, int, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if TEMPLATE_DIR in path.parents or path == TEMPLATE_DIR:
            continue
        if path.suffix.lower() not in {".yaml", ".yml", ".py", ".md", ".toml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if PLACEHOLDER in line:
                offenders.append((path, lineno, line.strip()))
    return offenders


def _validate_configs(root: Path) -> list[str]:
    """Run the strict config validator over every submission config found.

    The evaluation workflow validates the one submission it is about to run,
    bound to the directory the PR touched. This is the cheaper, earlier signal:
    it runs on every PR with no secrets in scope, so a contributor sees a
    malformed config immediately instead of after a maintainer applies a label.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ruamel.yaml import YAML
    from validate_submission_config import ConfigError, validate_config

    problems: list[str] = []
    for cfg_path in sorted(root.glob("*/*/config.yaml")):
        if TEMPLATE_DIR in cfg_path.parents:
            continue
        submission_dir = cfg_path.parent.as_posix()
        try:
            raw = YAML(typ="safe").load(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append(f"{cfg_path}: unparsable YAML: {exc}")
            continue
        try:
            validate_config(raw, expected_dir=submission_dir)
        except ConfigError as exc:
            problems.append(f"{cfg_path}: {exc}")
    return problems


def main() -> int:
    root = Path("submissions")
    if not root.exists():
        print("No submissions/ directory found — nothing to validate.")
        return 0

    config_problems = _validate_configs(root)
    if config_problems:
        print("Submission validator FAILED — invalid config.yaml:")
        for problem in config_problems:
            print(f"  {problem}")
        return 1

    offenders = find_offenders(root)
    if not offenders:
        print("Submission validator: no unresolved FILL_ME placeholders.")
        return 0
    print("Submission validator FAILED — please edit the template placeholders:")
    for path, lineno, line in offenders:
        print(f"  {path}:{lineno}: {line}")
    print(
        "\nEvery `FILL_ME` in submissions/ (outside _template/) must be replaced "
        "before the submission can be evaluated."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
