"""Mechanical scoring of the reader's structured answers.

No LLM judge, no substring heuristics: a choice is an option letter, a value
is normalized by its kind and compared exactly, and select-all answers are
scored so that hedging can't pay —

    score = max(0, (right picks - wrong picks) / right answers)

— so selecting every option scores at most what selecting none would, once
there are at least as many wrong options as right ones (which the generators
guarantee).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import date, datetime
from typing import Literal, cast

from compactbench.contracts import NOT_STATED, Probe, ProbeFormat, ProbeResult, ValueKind

NOT_STATED_TOKEN = "NOT_STATED"
_NOT_STATED_ALIASES = frozenset(
    {
        "not_stated",
        "not stated",
        "notstated",
        "not stated in the conversation",
        "unknown",
        "n/a",
        "none",
        "not mentioned",
        "not specified",
    }
)
_LETTER = re.compile(r"^\(?([A-Za-z])\)?(?:[.):\s]|$)")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%B %d, %Y",
    "%B %d %Y",
    "%d %B %Y",
    "%d %B, %Y",
    "%b %d %Y",
    "%b %d, %Y",
    "%d %b %Y",
    "%Y/%m/%d",
)
_ARTICLE = re.compile(r"^(the|a|an)\s+")
_POSSESSIVE = re.compile(r"^[\w\-]+'s\s+")


def option_letter(index: int) -> str:
    """``0 -> "A"``, ``1 -> "B"`` …"""
    return chr(ord("A") + index)


def is_not_stated(raw: str) -> bool:
    return raw.strip().strip(".").casefold() in _NOT_STATED_ALIASES


def normalize(value: str, kind: ValueKind) -> str:
    """Canonical form of ``value`` for exact comparison under ``kind``."""
    text = unicodedata.normalize("NFKC", value).strip().strip("\"'`").strip()
    if kind in (ValueKind.NUMBER, ValueKind.MONEY):
        return _normalize_number(text)
    if kind == ValueKind.DATE:
        return _normalize_date(text)
    if kind == ValueKind.IDENT:
        return re.sub(r"[^0-9A-Za-z]", "", text).upper()
    if kind == ValueKind.VERSION:
        return re.sub(r"\s+", "", text).lower().removeprefix("version").lstrip("v")
    folded = re.sub(r"\s+", " ", text.casefold()).strip(" .;:,!")
    if kind == ValueKind.TEXT:
        folded = _ARTICLE.sub("", folded)
        folded = _POSSESSIVE.sub("", folded)
        folded = _ARTICLE.sub("", folded)
    return folded


def _normalize_number(text: str) -> str:
    cleaned = text.replace(",", "").replace("$", "").replace("USD", "").strip()
    match = _NUMBER.search(cleaned)
    if match is None:
        return cleaned.casefold()
    number = float(match.group(0))
    suffix = cleaned[match.end() : match.end() + 1].casefold()
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _normalize_date(text: str) -> str:
    candidate = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return date.fromisoformat(candidate[:10]).isoformat()
    except ValueError:
        return candidate.casefold()


def _as_strings(raw: object) -> list[str] | None:
    """Coerce a reader answer into a list of strings (``None`` if it has no usable shape)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return [str(raw)]
    if isinstance(raw, list):
        items = cast("list[object]", raw)
        out: list[str] = []
        for item in items:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, int | float) and not isinstance(item, bool):
                out.append(str(item))
            else:
                return None
        return out
    return None


def _split_list(values: list[str]) -> list[str]:
    """Accept ``["A, C"]`` as well as ``["A", "C"]``."""
    out: list[str] = []
    for value in values:
        parts = [p.strip() for p in re.split(r"[,;\n]", value)] if len(values) == 1 else [value]
        out.extend(p for p in parts if p)
    return out


def _resolve_options(probe: Probe, picks: list[str]) -> list[str] | None:
    """Map letters (or exact option texts) to option texts; ``None`` if any pick is unknown."""
    by_text = {opt.casefold(): opt for opt in probe.options}
    resolved: list[str] = []
    for pick in picks:
        text = pick.strip()
        if text.casefold() in by_text:
            resolved.append(by_text[text.casefold()])
            continue
        match = _LETTER.match(text)
        if match is not None:
            index = ord(match.group(1).upper()) - ord("A")
            if 0 <= index < len(probe.options):
                resolved.append(probe.options[index])
                continue
        return None
    return list(dict.fromkeys(resolved))


def _set_score(picked: set[str], correct: set[str]) -> float:
    if not correct:
        return 1.0 if not picked else 0.0
    right = len(picked & correct)
    wrong = len(picked - correct)
    return max(0.0, (right - wrong) / len(correct))


Arm = Literal["score", "oracle_score", "null_score"]


def counted(results: Iterable[ProbeResult], arm: Arm = "score") -> list[float]:
    """The probe scores that count toward a score, for the method or a control arm.

    A probe whose right answer is "not stated" (or an empty selection) earns
    nothing when answered right — an empty context would answer it right too —
    so it is left out; answered wrong, it counts as a miss. Abstention probes
    can only cost a method points, never pad its score. Probes without a score
    for ``arm`` (controls off) are skipped.
    """
    out: list[float] = []
    for r in results:
        value: float | None = getattr(r, arm)
        if value is None or (r.expects_abstention and value >= 1.0):
            continue
        out.append(value)
    return out


def score_probe(probe: Probe, raw: object) -> ProbeResult:
    """Score the reader's ``raw`` answer to ``probe``."""
    expects_abstention = probe.answer in ([NOT_STATED], [])

    def result(
        score: float,
        answered: bool,
        *,
        stale: bool = False,
        abstained: bool = False,
        trapped: bool = False,
    ) -> ProbeResult:
        return ProbeResult(
            key=probe.key,
            category=probe.category.value,
            format=probe.format.value,
            origin_cycle=probe.origin_cycle,
            score=score,
            answered=answered,
            stale=stale,
            abstained=abstained,
            expects_abstention=expects_abstention,
            stale_possible=bool(probe.stale),
            trapped=trapped,
            trap_possible=bool(probe.traps),
            family=probe.family,
        )

    strings = _as_strings(raw)
    if strings is None:
        return result(0.0, answered=False)

    if probe.format == ProbeFormat.SINGLE:
        picks = _resolve_options(probe, strings) or _resolve_options(probe, _split_list(strings))
        if picks is None or not picks:
            return result(0.0, answered=False)
        if len(picks) > 1:
            return result(0.0, answered=True)
        pick = picks[0]
        return result(
            1.0 if pick == probe.answer[0] else 0.0,
            answered=True,
            stale=pick in probe.stale,
            abstained=pick == NOT_STATED,
            trapped=pick in probe.traps,
        )

    if probe.format == ProbeFormat.MULTI:
        picks = (
            []
            if strings == []
            else _resolve_options(probe, strings) or _resolve_options(probe, _split_list(strings))
        )
        if picks is None:
            return result(0.0, answered=False)
        picked = set(picks)
        return result(
            _set_score(picked, set(probe.answer)),
            answered=True,
            stale=bool(picked & set(probe.stale)),
            trapped=bool(picked & set(probe.traps)),
        )

    if probe.format == ProbeFormat.VALUE:
        if len(strings) != 1:
            return result(0.0, answered=bool(strings))
        given = strings[0]
        if is_not_stated(given):
            return result(1.0 if expects_abstention else 0.0, answered=True, abstained=True)
        if expects_abstention:
            return result(0.0, answered=True)
        value = normalize(given, probe.value_kind)
        stale = {normalize(s, probe.value_kind) for s in probe.stale}
        traps = {normalize(t, probe.value_kind) for t in probe.traps}
        return result(
            1.0 if value == normalize(probe.answer[0], probe.value_kind) else 0.0,
            answered=True,
            stale=value in stale,
            trapped=value in traps,
        )

    values = _split_list(strings)
    if len(values) == 1 and is_not_stated(values[0]):
        return result(1.0 if not probe.answer else 0.0, answered=True, abstained=True)
    picked = {normalize(v, probe.value_kind) for v in values}
    correct = {normalize(v, probe.value_kind) for v in probe.answer}
    stale = {normalize(v, probe.value_kind) for v in probe.stale}
    traps = {normalize(v, probe.value_kind) for v in probe.traps}
    return result(
        _set_score(picked, correct),
        answered=True,
        stale=bool(picked & stale),
        trapped=bool(picked & traps),
    )
