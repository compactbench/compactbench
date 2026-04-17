"""Compression-ratio computation using the ``cl100k_base`` tokenizer.

Using a single canonical tokenizer regardless of the target model keeps
compression ratios directly comparable across methods and leaderboard
versions (see docs/architecture/decisions.md §B3).
"""

from __future__ import annotations

from typing import Any

import tiktoken

from compactbench.contracts import CompactionArtifact, Transcript

_ENCODER_CACHE: dict[str, Any] = {}


def _encoder(name: str = "cl100k_base") -> Any:
    enc = _ENCODER_CACHE.get(name)
    if enc is None:
        enc = tiktoken.get_encoding(name)
        _ENCODER_CACHE[name] = enc
    return enc


def count_tokens(text: str, encoding: str = "cl100k_base") -> int:
    """Return the number of tokens in ``text`` under the given ``encoding``."""
    if not text:
        return 0
    return len(_encoder(encoding).encode(text))


def transcript_tokens(transcript: Transcript) -> int:
    """Sum of token counts across every turn's content."""
    return sum(count_tokens(t.content) for t in transcript.turns)


def artifact_tokens(artifact: CompactionArtifact) -> int:
    """Sum of tokens across the artifact's summary text and structured state values."""
    total = count_tokens(artifact.summary_text)
    state = artifact.structured_state
    for section in (
        state.immutable_facts,
        state.locked_decisions,
        state.deferred_items,
        state.forbidden_behaviors,
        state.unresolved_items,
    ):
        for s in section:
            total += count_tokens(s)
    for k, v in state.entity_map.items():
        total += count_tokens(k) + count_tokens(v)
    return total


def compression_ratio(transcript: Transcript, artifact: CompactionArtifact) -> float:
    """Return ``tokens(transcript) / tokens(artifact)``.

    If the artifact has zero tokens, the denominator is floored at 1 to keep
    the ratio finite; the caller can detect this by checking that
    :func:`artifact_tokens` is zero.
    """
    src = transcript_tokens(transcript)
    dst = artifact_tokens(artifact)
    return src / max(dst, 1)
