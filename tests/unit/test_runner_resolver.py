"""Method-resolver tests."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from compactbench.compactors import HybridLedgerCompactor, NaiveSummaryCompactor
from compactbench.runner import MethodResolutionError, resolve_compactor_class

pytestmark = pytest.mark.unit


def test_resolves_built_in_key() -> None:
    assert resolve_compactor_class("built-in:naive-summary") is NaiveSummaryCompactor


def test_resolves_another_built_in() -> None:
    assert resolve_compactor_class("built-in:hybrid-ledger") is HybridLedgerCompactor


def test_raises_on_unknown_built_in() -> None:
    with pytest.raises(MethodResolutionError, match="unknown built-in"):
        resolve_compactor_class("built-in:not-real")


def test_raises_on_malformed_spec() -> None:
    with pytest.raises(MethodResolutionError, match="could not resolve"):
        resolve_compactor_class("bare-name")


def test_raises_on_missing_file() -> None:
    with pytest.raises(MethodResolutionError, match="not found"):
        resolve_compactor_class("/does/not/exist.py:MyCompactor")


def test_raises_on_non_py_file(tmp_path: Path) -> None:
    txt = tmp_path / "compactor.txt"
    txt.write_text("not python", encoding="utf-8")
    with pytest.raises(MethodResolutionError, match=r"\.py file"):
        resolve_compactor_class(f"{txt}:MyCompactor")


def test_loads_custom_class_from_file(tmp_path: Path) -> None:
    source = dedent(
        """
        from typing import Any, ClassVar
        from compactbench.compactors import Compactor
        from compactbench.contracts import CompactionArtifact, StructuredState, Transcript

        class MyCompactor(Compactor):
            name: ClassVar[str] = "my-method"
            version: ClassVar[str] = "0.0.1"

            async def compact(
                self, transcript: Transcript,
                config: dict[str, Any] | None = None,
                previous_artifact: CompactionArtifact | None = None,
            ) -> CompactionArtifact:
                return CompactionArtifact()
        """
    )
    py = tmp_path / "my_compactor.py"
    py.write_text(source, encoding="utf-8")
    cls = resolve_compactor_class(f"{py}:MyCompactor")
    assert cls.__name__ == "MyCompactor"
    assert cls.name == "my-method"


def test_raises_on_missing_class_in_file(tmp_path: Path) -> None:
    py = tmp_path / "m.py"
    py.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(MethodResolutionError, match="not found"):
        resolve_compactor_class(f"{py}:Nope")


def test_raises_on_non_compactor_class(tmp_path: Path) -> None:
    py = tmp_path / "m.py"
    py.write_text("class NotACompactor:\n    pass\n", encoding="utf-8")
    with pytest.raises(MethodResolutionError, match="subclass of Compactor"):
        resolve_compactor_class(f"{py}:NotACompactor")
