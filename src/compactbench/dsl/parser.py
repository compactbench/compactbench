"""Parse YAML template files into :class:`TemplateDefinition` models."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from compactbench.dsl.errors import TemplateParseError
from compactbench.dsl.models import TemplateDefinition

_yaml = YAML(typ="safe")


def parse_template_file(path: Path | str) -> TemplateDefinition:
    """Load a template YAML file from disk and return a validated model."""
    path = Path(path)
    if not path.exists():
        raise TemplateParseError(f"template file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = _yaml.load(f)  # pyright: ignore[reportUnknownMemberType]
    except YAMLError as exc:
        raise TemplateParseError(f"YAML syntax error in {path}: {exc}") from exc
    return _build_definition(data, source=str(path))


def parse_template_string(yaml_text: str) -> TemplateDefinition:
    """Parse a template from a YAML string (used in tests)."""
    try:
        data = _yaml.load(yaml_text)  # pyright: ignore[reportUnknownMemberType]
    except YAMLError as exc:
        raise TemplateParseError(f"YAML syntax error: {exc}") from exc
    return _build_definition(data, source="<string>")


def load_suite(suite_dir: Path | str) -> list[TemplateDefinition]:
    """Load every ``*.yaml`` template in a suite directory, sorted by filename."""
    suite_dir = Path(suite_dir)
    if not suite_dir.is_dir():
        raise TemplateParseError(f"not a directory: {suite_dir}")
    return [parse_template_file(p) for p in sorted(suite_dir.glob("*.yaml"))]


def _build_definition(data: object, source: str) -> TemplateDefinition:
    if not isinstance(data, dict):
        raise TemplateParseError(f"expected a YAML mapping at root of {source}")
    if "template" not in data:
        raise TemplateParseError(f"missing 'template' key at root of {source}")
    try:
        return TemplateDefinition.model_validate(data["template"])
    except ValidationError as exc:
        raise TemplateParseError(f"structural validation failed for {source}:\n{exc}") from exc
