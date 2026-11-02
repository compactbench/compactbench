"""Seasons: the pinned configuration every ranked run in a leaderboard season uses.

A season fixes everything that affects a score — suite and version,
difficulty, drift cycles, cases per family, token budget, reader model,
controls — so submitters choose only their method and the model it uses.
Ranked runs are checked against their season before they can be published.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from ruamel.yaml import YAML

from compactbench.contracts import RunResult
from compactbench.scenarios import Difficulty


class ReaderSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str
    effort: Literal["low", "medium", "high"] | None = None


class Season(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    suite: str
    suite_version: str
    difficulty: Difficulty
    drift_cycles: int = Field(ge=1)
    cases_per_family: int = Field(ge=1)
    budget_tokens: int = Field(ge=1)
    reader: ReaderSpec
    controls: bool = True
    sampling: Literal["fixed", "fresh"] = "fixed"
    """``fresh``: every ranked run gets its own sample from the suite's generator."""
    seed_group: str = "default"
    suite_pack: str | None = None
    """Path (relative to the season file) of a private suite pack to load first."""
    public_key: str | None = None
    """Season public key; submitters seal their provider key to it (``keys seal``)."""


def load_season(path: Path) -> Season:
    yaml = YAML(typ="safe")
    with path.open(encoding="utf-8") as fp:
        data: object = yaml.load(fp)  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(data, dict):
        raise ValueError(f"{path}: a season file must be a mapping")
    return Season.model_validate(data)


def season_mismatches(run: RunResult, season: Season) -> list[str]:
    """Every way ``run`` departs from ``season``'s pinned configuration."""
    expected: dict[str, object] = {
        "season": season.key,
        "suite": season.suite,
        "suite_version": season.suite_version,
        "difficulty": season.difficulty.value,
        "drift_cycles": season.drift_cycles,
        "cases_per_family": season.cases_per_family,
        "budget_tokens": season.budget_tokens,
        "reader_provider": season.reader.provider,
        "reader_model": season.reader.model,
        "reader_effort": season.reader.effort,
        "controls": season.controls,
    }
    if season.sampling == "fixed":
        expected["seed_group"] = season.seed_group
    return [
        f"{name} is {getattr(run, name)!r}, season {season.key} requires {value!r}"
        for name, value in expected.items()
        if getattr(run, name) != value
    ]
