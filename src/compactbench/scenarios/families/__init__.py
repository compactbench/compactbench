"""Scenario families. Importing this package registers the public families."""

from compactbench.scenarios.families import (
    buried_constraint,
    conditional_scope,
    decision_override,
    entity_confusion,
    numeric_precision,
    provenance_authority,
    reference_resolution,
    task_continuity,
)
from compactbench.scenarios.families.base import (
    Family,
    UnknownFamilyError,
    get_family,
    list_families,
    register_family,
    say,
)
from compactbench.scenarios.families.mixed import MixedSession

PUBLIC_FAMILIES: tuple[str, ...] = (
    buried_constraint.BuriedConstraint.key,
    decision_override.DecisionOverride.key,
    entity_confusion.EntityConfusion.key,
    reference_resolution.ReferenceResolution.key,
    numeric_precision.NumericPrecision.key,
    conditional_scope.ConditionalScope.key,
    task_continuity.TaskContinuity.key,
    provenance_authority.ProvenanceAuthority.key,
)

MIXED = register_family(MixedSession(PUBLIC_FAMILIES))
"""Every public family in one conversation (key ``"mixed"``)."""

__all__ = [
    "MIXED",
    "PUBLIC_FAMILIES",
    "Family",
    "MixedSession",
    "UnknownFamilyError",
    "get_family",
    "list_families",
    "register_family",
    "say",
]
