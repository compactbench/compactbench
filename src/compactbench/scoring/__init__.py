"""Scoring: mechanical answer checks and run-level metrics.

See docs/methodology.md for every definition.
"""

from compactbench.scoring.answers import (
    NOT_STATED_TOKEN,
    counted,
    is_not_stated,
    normalize,
    option_letter,
    score_probe,
)
from compactbench.scoring.metrics import compute_metrics

__all__ = [
    "NOT_STATED_TOKEN",
    "compute_metrics",
    "counted",
    "is_not_stated",
    "normalize",
    "option_letter",
    "score_probe",
]
