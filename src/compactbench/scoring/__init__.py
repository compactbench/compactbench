"""Scoring engine: checks, weighted aggregation, drift, contradictions, compression.

See docs/architecture/decisions.md §B3 for formulas and weights.
Implemented in WO-004.
"""

from compactbench.scoring.checks import (
    contains_normalized,
    exact,
    forbidden_absent,
    run_check,
    set_match,
)
from compactbench.scoring.compression import (
    artifact_tokens,
    compression_ratio,
    count_tokens,
    transcript_tokens,
)
from compactbench.scoring.contradictions import (
    contradiction_rate,
    count_violations,
    response_violates,
)
from compactbench.scoring.drift import drift_deltas, drift_resistance
from compactbench.scoring.errors import ScoringError
from compactbench.scoring.scorer import WEIGHTS, score_cycle, score_item

__all__ = [
    "WEIGHTS",
    "ScoringError",
    "artifact_tokens",
    "compression_ratio",
    "contains_normalized",
    "contradiction_rate",
    "count_tokens",
    "count_violations",
    "drift_deltas",
    "drift_resistance",
    "exact",
    "forbidden_absent",
    "response_violates",
    "run_check",
    "score_cycle",
    "score_item",
    "set_match",
    "transcript_tokens",
]
