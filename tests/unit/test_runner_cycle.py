"""One compaction cycle: request shape, budget enforcement, reader, controls."""

from __future__ import annotations

from typing import ClassVar

import pytest

from compactbench.compactors import Compactor, NullCompactor, OracleCompactor
from compactbench.contracts import CompactionArtifact, CompactionRequest
from compactbench.providers import CountingProvider, MockProvider
from compactbench.runner.cycle import execute_cycle
from compactbench.scenarios import Difficulty, generate_case
from tests.helpers import AnswerKeyReader

pytestmark = pytest.mark.unit


class _Spy(Compactor):
    """Records every request; returns a fixed-size artifact."""

    name: ClassVar[str] = "spy"
    version: ClassVar[str] = "0"

    def __init__(self, provider: object, model: str, words: int = 10) -> None:
        super().__init__(provider, model)  # type: ignore[arg-type]
        self.requests: list[CompactionRequest] = []
        self.words = words

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        self.requests.append(request)
        return CompactionArtifact(summaryText=" ".join(["word"] * self.words))


def _case():
    """An easy case whose turns all carry a generation tag, as answer-bearing turns do."""
    case = generate_case("buried_constraint", 21, Difficulty.EASY)
    cycles = [
        spec.model_copy(
            update={"turns": [t.model_copy(update={"tags": ["embedded"]}) for t in spec.turns]}
        )
        for spec in case.cycles
    ]
    return case.model_copy(update={"cycles": cycles})


async def _run(compactor: Compactor, *, cycle: int = 0, budget: int | None = 500, **kw: object):
    case = _case()
    counting = CountingProvider(MockProvider())
    reader = CountingProvider(AnswerKeyReader([case], cycle=cycle))
    previous = CompactionArtifact(summaryText="prev") if cycle else None
    return await execute_cycle(
        case=case,
        cycle=cycle,
        previous_artifact=previous,
        compactor=compactor,
        compactor_provider=counting,
        reader=reader,
        reader_model="r",
        budget_tokens=budget,
        **kw,  # type: ignore[arg-type]
    )


async def test_method_never_sees_generation_tags() -> None:
    spy = _Spy(MockProvider(), "m")
    case = _case()
    assert any(t.tags for t in case.cycles[0].turns), "fixture should carry tags"
    await _run(spy)
    assert all(not t.tags for t in spy.requests[0].turns)


async def test_later_cycles_get_only_new_turns_and_previous_artifact() -> None:
    spy = _Spy(MockProvider(), "m")
    case = _case()
    await _run(spy, cycle=1)
    request = spy.requests[0]
    assert request.previous_artifact is not None
    assert [t.id for t in request.turns] == [t.id for t in case.cycles[1].turns]


async def test_oracle_with_perfect_reader_scores_full_marks() -> None:
    execution = await _run(OracleCompactor(MockProvider(), "m"), budget=None)
    assert execution.result.score == 1.0
    assert not execution.result.over_budget


async def test_over_budget_artifact_is_cut_and_flagged() -> None:
    execution = await _run(_Spy(MockProvider(), "m", words=400), budget=50)
    assert execution.result.over_budget
    assert execution.result.artifact_tokens > 50
    from compactbench.tokens import count_tokens

    assert count_tokens(execution.visible_context) <= 50


async def test_controls_bracket_the_method() -> None:
    execution = await _run(NullCompactor(MockProvider(), "m"), controls=True)
    assert execution.result.oracle_score == 1.0
    assert execution.result.null_score is not None
    assert execution.result.null_score <= 1.0
    assert execution.result.control_usage is not None


async def test_usage_and_warnings_are_recorded() -> None:
    class _Warns(_Spy):
        async def compact(self, request: CompactionRequest) -> CompactionArtifact:
            return CompactionArtifact(summaryText="x", warnings=["state JSON did not parse"])

    execution = await _run(_Warns(MockProvider(), "m"))
    assert execution.result.warnings == ["state JSON did not parse"]
    assert execution.result.reader_usage is not None
    assert execution.result.reader_usage.call_count >= 1
