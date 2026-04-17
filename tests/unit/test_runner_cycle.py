"""Single-cycle execution tests."""

from __future__ import annotations

import json

import pytest

from compactbench.compactors import NaiveSummaryCompactor
from compactbench.dsl import DifficultyLevel, parse_template_file
from compactbench.engine import generate_case
from compactbench.providers import MockProvider
from compactbench.runner.cycle import execute_cycle

pytestmark = pytest.mark.unit


def _load_starter_case() -> object:
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
    from compactbench.contracts import GeneratedCase

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
    from compactbench.contracts import CompactionArtifact, GeneratedCase, StructuredState

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
    from compactbench.contracts import GeneratedCase

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
    from compactbench.contracts import GeneratedCase

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
