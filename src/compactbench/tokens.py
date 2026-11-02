"""Canonical token counting (``cl100k_base``).

One tokenizer for every method, model and provider keeps budgets and
compression ratios comparable. It is a measuring stick, not a claim about any
particular model's tokenizer.
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken

ENCODING = "cl100k_base"


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING)


def count_tokens(text: str) -> int:
    """Number of ``cl100k_base`` tokens in ``text``."""
    if not text:
        return 0
    return len(_encoder().encode(text, disallowed_special=()))


def head_tokens(text: str, limit: int) -> str:
    """Return the longest prefix of ``text`` that is at most ``limit`` tokens."""
    if limit <= 0:
        return ""
    tokens = _encoder().encode(text, disallowed_special=())
    if len(tokens) <= limit:
        return text
    return _encoder().decode(tokens[:limit])


def tail_tokens(text: str, limit: int) -> str:
    """Return the longest suffix of ``text`` that is at most ``limit`` tokens."""
    if limit <= 0:
        return ""
    tokens = _encoder().encode(text, disallowed_special=())
    if len(tokens) <= limit:
        return text
    return _encoder().decode(tokens[-limit:])
