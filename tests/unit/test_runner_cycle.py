"""Single-cycle execution tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from compactbench.compactors import Compactor, NaiveSummaryCompactor
from compactbench.contracts import CompactionArtifact, GeneratedCase, Transcript
from compactbench.contracts.case import Turn, TurnRole
from compactbench.dsl import DifficultyLevel, parse_template_file
from compactbench.engine import generate_case
from compactbench.providers import MockProvider
from compactbench.runner.cycle import execute_cycle

pytestmark = pytest.mark.unit


def _load_starter_case() -> GeneratedCase:
    from pathlib import Path

    starter = Path(__file__).resolve().parents[2] / "benchmarks" / "public" / "starter"
    template = parse_template_file(starter / "buried_constraint_starter_v1.yaml")
    return generate_case(template, seed=42, difficulty=DifficultyLevel.MEDIUM)


def _mock_provider_for_run() -> MockProvider:
    # For naive-summary: 1 compact call + 3 eval calls (starter has 3 eval items).
    return MockProvider(
        default="clean response",
        responses=[
            "summary after compaction",  # compact call
            "clean response",  # eval q1
            "clean response",  # eval q2
            "clean response",  # eval q3
        ],
    )


async def test_cycle_zero_skips_continuation() -> None:

    case: GeneratedCase = _load_starter_case()  # type: ignore[assignment]
    provider = _mock_provider_for_run()
    compactor = NaiveSummaryCompactor(provider, model="m")
    result = await execute_cycle(
        case=case,
        transcript=case.transcript,
        cycle_number=0,
        previous_artifact=None,
        compactor=compactor,
        provider=provider,
        model="m",
        case_seed=42,
    )
    # At cycle 0, transcript passthrough — no continuation turns appended.
    assert len(result.extended_transcript.turns) == len(case.transcript.turns)
    assert result.scorecard.cycle_number == 0
    assert result.artifact is not None


async def test_cycle_one_adds_continuation_turns() -> None:
    from compactbench.contracts import CompactionArtifact, StructuredState

    case: GeneratedCase = _load_starter_case()  # type: ignore[assignment]
    # For cycle 1: 1 continuation call + 1 compact call + 3 eval calls = 5 responses
    provider = MockProvider(
        default="fallback",
        responses=[
            "assistant continuation response",
            "recompacted summary",
            "clean",
            "clean",
            "clean",
        ],
    )
    compactor = NaiveSummaryCompactor(provider, model="m")
    prior = CompactionArtifact(summaryText="prior", structured_state=StructuredState())
    result = await execute_cycle(
        case=case,
        transcript=case.transcript,
        cycle_number=1,
        previous_artifact=prior,
        compactor=compactor,
        provider=provider,
        model="m",
        case_seed=42,
    )
    # Extended transcript should have 2 more turns than the original.
    assert len(result.extended_transcript.turns) == len(case.transcript.turns) + 2
    assert result.scorecard.cycle_number == 1


async def test_cycle_records_latency() -> None:

    case: GeneratedCase = _load_starter_case()  # type: ignore[assignment]
    provider = _mock_provider_for_run()
    compactor = NaiveSummaryCompactor(provider, model="m")
    result = await execute_cycle(
        case=case,
        transcript=case.transcript,
        cycle_number=0,
        previous_artifact=None,
        compactor=compactor,
        provider=provider,
        model="m",
        case_seed=42,
    )
    assert result.latency_ms >= 0


async def test_cycle_produces_valid_json_serializable_artifact() -> None:

    case: GeneratedCase = _load_starter_case()  # type: ignore[assignment]
    provider = _mock_provider_for_run()
    compactor = NaiveSummaryCompactor(provider, model="m")
    result = await execute_cycle(
        case=case,
        transcript=case.transcript,
        cycle_number=0,
        previous_artifact=None,
        compactor=compactor,
        provider=provider,
        model="m",
        case_seed=42,
    )
    # Round-trip through JSON to confirm shape.
    serialized = result.artifact.model_dump_json()
    parsed = json.loads(serialized)
    assert "structured_state" in parsed


async def test_compactor_never_sees_turn_tags() -> None:
    """Generation metadata must not reach the method — it is the answer key.

    `tags` marks which turns are distractors and which carries the constraint.
    A method that simply keeps the non-`distractor` turns recovers every recall
    item at high compression with no model call at all, which would top the
    leaderboard while doing nothing a compactor does. Tags stay on the generated
    case for diagnostics; the runner strips them at the compaction boundary.
    """
    seen: list[str] = []

    class _TagSpy(Compactor):
        name = "tag-spy"
        version = "1.0.0"

        async def compact(
            self,
            transcript: Transcript,
            config: dict[str, Any] | None = None,
            previous_artifact: CompactionArtifact | None = None,
        ) -> CompactionArtifact:
            for turn in transcript.turns:
                seen.extend(turn.tags)
            return CompactionArtifact(summaryText="x")

    case = _load_starter_case()
    assert any(t.tags for t in case.transcript.turns), "fixture must actually carry tags"

    provider = MockProvider()
    await execute_cycle(
        case=case,
        compactor=_TagSpy(provider, "m"),
        provider=provider,
        model="m",
        transcript=case.transcript,
        cycle_number=0,
        previous_artifact=None,
        case_seed=1,
    )

    assert seen == []


def test_without_tags_leaves_content_and_roles_intact() -> None:
    """Stripping tags must not perturb what is actually being compacted."""
    original = Transcript(
        turns=[
            Turn(id=0, role=TurnRole.USER, content="keep this", tags=["critical_constraint"]),
            Turn(id=1, role=TurnRole.ASSISTANT, content="and this", tags=["distractor"]),
        ]
    )
    stripped = original.without_tags()
    assert [t.tags for t in stripped.turns] == [[], []]
    assert [(t.id, t.role, t.content) for t in stripped.turns] == [
        (t.id, t.role, t.content) for t in original.turns
    ]
    # Source is frozen and must be unchanged — scoring and diagnostics still use it.
    assert [t.tags for t in original.turns] == [["critical_constraint"], ["distractor"]]
