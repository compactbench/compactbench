"""Shared builders for tests."""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from typing import ClassVar

from compactbench.contracts import (
    CompactionArtifact,
    CompactionRequest,
    GeneratedCase,
    Probe,
    ProbeFormat,
    Transcript,
)
from compactbench.providers import CompletionRequest, CompletionResponse, Provider
from compactbench.scoring.answers import NOT_STATED_TOKEN, option_letter


def first_request(transcript: Transcript, *, budget: int | None = None) -> CompactionRequest:
    """The cycle-0 request for ``transcript``."""
    return CompactionRequest(cycle=0, turns=list(transcript.turns), token_budget=budget)


def next_request(
    transcript: Transcript,
    previous: CompactionArtifact,
    *,
    cycle: int = 1,
    budget: int | None = None,
) -> CompactionRequest:
    """A later-cycle request: ``transcript`` holds only the new turns."""
    return CompactionRequest(
        cycle=cycle, turns=list(transcript.turns), previous_artifact=previous, token_budget=budget
    )


_BLOCK = re.compile(r"^(Q\d+) \([^)]*\): (.*)$")
_OPTION = re.compile(r"^\s+([A-Z])\. (.*)$")


def _parse_questions(prompt: str) -> list[tuple[str, str, list[str]]]:
    """``(qid, question, options)`` for every question in a reader prompt."""
    out: list[tuple[str, str, list[str]]] = []
    for line in prompt.splitlines():
        head = _BLOCK.match(line)
        if head is not None:
            out.append((head.group(1), head.group(2), []))
            continue
        option = _OPTION.match(line)
        if option is not None and out:
            out[-1][2].append(option.group(2))
    return out


class AnswerKeyReader(Provider):
    """A reader that answers from the cases' answer key (or always says 'not stated').

    The same question can have different answers at different cycles, so by
    default each repeat of a question takes the next cycle's answer — which is
    exact when cases run one at a time (``concurrency=1``) without controls.
    Pass ``cycle`` to answer every question as of that one cycle instead.
    """

    key: ClassVar[str] = "answer-key"

    def __init__(
        self,
        cases: list[GeneratedCase],
        *,
        know_nothing: bool = False,
        cycle: int | None = None,
    ) -> None:
        self._queues: dict[tuple[str, tuple[str, ...]], deque[Probe]] = defaultdict(deque)
        for case in cases:
            for spec in case.cycles:
                if cycle is not None and spec.cycle != cycle:
                    continue
                for probe in spec.probes:
                    self._queues[(probe.question, tuple(probe.options))].append(probe)
        self._know_nothing = know_nothing
        self.calls = 0

    def _next(self, key: tuple[str, tuple[str, ...]]) -> Probe | None:
        queue = self._queues.get(key)
        if not queue:
            return None
        return queue.popleft() if len(queue) > 1 else queue[0]

    def _answer(self, probe: Probe) -> object:
        if probe.format == ProbeFormat.SINGLE:
            index = (
                len(probe.options) - 1
                if self._know_nothing
                else probe.options.index(probe.answer[0])
            )
            return option_letter(index)
        if probe.format == ProbeFormat.MULTI:
            if self._know_nothing:
                return []
            return [option_letter(probe.options.index(a)) for a in probe.answer]
        if probe.format == ProbeFormat.VALUE:
            return NOT_STATED_TOKEN if self._know_nothing else probe.answer[0]
        return [NOT_STATED_TOKEN] if self._know_nothing else list(probe.answer)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.calls += 1
        answers: dict[str, object] = {}
        for qid, question, options in _parse_questions(request.prompt):
            probe = self._next((question, tuple(options)))
            if probe is not None:
                answers[qid] = self._answer(probe)
        text = json.dumps(answers)
        return CompletionResponse(
            text=text,
            prompt_tokens=max(1, len(request.prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            model=request.model,
        )
