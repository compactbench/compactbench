"""Parser tests — valid templates, structural failures, file I/O."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from compactbench.dsl import (
    TemplateParseError,
    load_suite,
    parse_template_file,
    parse_template_string,
)

pytestmark = pytest.mark.unit


_MINIMAL_TEMPLATE = dedent(
    """
    template:
      key: sample_v1
      family: sample
      version: 1.0.0
      difficulty_policy: {}
      transcript:
        turns:
          - role: user
            template: "hello"
      ground_truth: {}
      evaluation_items:
        - key: q1
          type: planning_soundness
          prompt: "what is the answer?"
          expected:
            check: contains_normalized
            value: "yes"
    """
)


def test_parse_minimal_template_succeeds() -> None:
    t = parse_template_string(_MINIMAL_TEMPLATE)
    assert t.key == "sample_v1"
    assert t.family == "sample"
    assert t.version == "1.0.0"
    assert len(t.transcript.turns) == 1
    assert len(t.evaluation_items) == 1


def test_parse_raises_on_missing_template_root() -> None:
    with pytest.raises(TemplateParseError, match="missing 'template' key"):
        parse_template_string("key: standalone\nfamily: x\n")


def test_parse_raises_on_invalid_yaml() -> None:
    # Unclosed flow mapping triggers a real YAML syntax error.
    with pytest.raises(TemplateParseError, match="YAML syntax error"):
        parse_template_string("template: {key: value")


def test_parse_rejects_extra_fields() -> None:
    yaml_text = _MINIMAL_TEMPLATE.replace(
        "  key: sample_v1",
        "  key: sample_v1\n  extra_field: nope",
    )
    with pytest.raises(TemplateParseError):
        parse_template_string(yaml_text)


def test_parse_rejects_missing_required_field() -> None:
    yaml_text = dedent(
        """
        template:
          family: sample
          version: 1.0.0
          difficulty_policy: {}
          transcript:
            turns: []
          ground_truth: {}
          evaluation_items:
            - key: q1
              type: planning_soundness
              prompt: x
              expected: {}
        """
    )
    with pytest.raises(TemplateParseError):
        parse_template_string(yaml_text)


def test_parse_rejects_bad_version_format() -> None:
    yaml_text = _MINIMAL_TEMPLATE.replace("1.0.0", "v1")
    with pytest.raises(TemplateParseError):
        parse_template_string(yaml_text)


def test_parse_rejects_bad_role() -> None:
    yaml_text = _MINIMAL_TEMPLATE.replace("role: user", "role: not_a_real_role")
    with pytest.raises(TemplateParseError):
        parse_template_string(yaml_text)


def test_parse_file_not_found() -> None:
    with pytest.raises(TemplateParseError, match="not found"):
        parse_template_file("/does/not/exist.yaml")


def test_parse_file_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    path.write_text(_MINIMAL_TEMPLATE, encoding="utf-8")
    t = parse_template_file(path)
    assert t.key == "sample_v1"


def test_distractor_block_requires_count() -> None:
    yaml_text = dedent(
        """
        template:
          key: needs_count_v1
          family: sample
          version: 1.0.0
          difficulty_policy: {}
          transcript:
            turns:
              - role: distractor_block
          ground_truth: {}
          evaluation_items:
            - key: q1
              type: planning_soundness
              prompt: x
              expected: {}
        """
    )
    with pytest.raises(TemplateParseError):
        parse_template_string(yaml_text)


def test_text_role_requires_template() -> None:
    yaml_text = dedent(
        """
        template:
          key: no_text_v1
          family: sample
          version: 1.0.0
          difficulty_policy: {}
          transcript:
            turns:
              - role: user
          ground_truth: {}
          evaluation_items:
            - key: q1
              type: planning_soundness
              prompt: x
              expected: {}
        """
    )
    with pytest.raises(TemplateParseError):
        parse_template_string(yaml_text)


# ---------------------------------------------------------------------------
# Suite loading + starter templates
# ---------------------------------------------------------------------------


_STARTER_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "public" / "starter"


def test_load_suite_reads_all_yaml_files(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(
        _MINIMAL_TEMPLATE.replace("sample_v1", "a_v1"), encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        _MINIMAL_TEMPLATE.replace("sample_v1", "b_v1"), encoding="utf-8"
    )
    (tmp_path / "readme.md").write_text("not yaml", encoding="utf-8")
    results = load_suite(tmp_path)
    assert [t.key for t in results] == ["a_v1", "b_v1"]


def test_load_suite_empty_dir(tmp_path: Path) -> None:
    assert load_suite(tmp_path) == []


def test_load_suite_on_missing_dir() -> None:
    with pytest.raises(TemplateParseError):
        load_suite("/not/a/real/dir")


def test_starter_suite_parses() -> None:
    templates = load_suite(_STARTER_DIR)
    assert len(templates) == 4
    keys = {t.key for t in templates}
    assert {
        "buried_constraint_starter_v1",
        "decision_override_starter_v1",
        "entity_confusion_starter_v1",
        "reference_resolution_starter_v1",
    } == keys
