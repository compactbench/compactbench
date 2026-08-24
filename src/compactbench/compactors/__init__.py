"""Built-in compaction methods and the ``Compactor`` ABC that custom methods extend.

Built-in keys are registered here; external methods subclass :class:`Compactor`
and are loaded by file path in WO-007 (runner).
"""

from compactbench.compactors.base import Compactor
from compactbench.compactors.controls import (
    NullCompactor,
    OracleCompactor,
    TruncateLastNCompactor,
)
from compactbench.compactors.errors import CompactorError, UnknownCompactorError
from compactbench.compactors.hierarchical_summary import HierarchicalSummaryCompactor
from compactbench.compactors.hybrid_ledger import HybridLedgerCompactor
from compactbench.compactors.naive_summary import NaiveSummaryCompactor
from compactbench.compactors.structured_state import StructuredStateCompactor

_BUILT_IN: dict[str, type[Compactor]] = {
    NaiveSummaryCompactor.name: NaiveSummaryCompactor,
    StructuredStateCompactor.name: StructuredStateCompactor,
    HierarchicalSummaryCompactor.name: HierarchicalSummaryCompactor,
    HybridLedgerCompactor.name: HybridLedgerCompactor,
    # Control arms. Not compaction methods — reference points that make every
    # other score readable. Cheap enough (zero model calls) to run every time.
    OracleCompactor.name: OracleCompactor,
    NullCompactor.name: NullCompactor,
    TruncateLastNCompactor.name: TruncateLastNCompactor,
}

#: Keys that are controls rather than competing methods. The leaderboard shows
#: them as reference rows and never ranks them against submissions.
CONTROL_KEYS: frozenset[str] = frozenset(
    {OracleCompactor.name, NullCompactor.name, TruncateLastNCompactor.name}
)


def list_built_ins() -> list[str]:
    """Return the sorted list of built-in compactor keys."""
    return sorted(_BUILT_IN)


def get_built_in(key: str) -> type[Compactor]:
    """Return the compactor class for ``key`` or raise :class:`UnknownCompactorError`."""
    cls = _BUILT_IN.get(key)
    if cls is None:
        raise UnknownCompactorError(
            f"unknown built-in compactor {key!r}. Known: {sorted(_BUILT_IN)}"
        )
    return cls


__all__ = [
    "CONTROL_KEYS",
    "Compactor",
    "CompactorError",
    "HierarchicalSummaryCompactor",
    "HybridLedgerCompactor",
    "NaiveSummaryCompactor",
    "NullCompactor",
    "OracleCompactor",
    "StructuredStateCompactor",
    "TruncateLastNCompactor",
    "UnknownCompactorError",
    "get_built_in",
    "list_built_ins",
]
