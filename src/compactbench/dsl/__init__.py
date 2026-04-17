"""Template DSL: parser, seeded generators, validator, substitution.

See docs/architecture/decisions.md §B1 for the DSL shape.
Implemented in WO-002.
"""

from compactbench.dsl.errors import (
    TemplateError,
    TemplateParseError,
    TemplateValidationError,
    UnknownGeneratorError,
    UnresolvedReferenceError,
)
from compactbench.dsl.generators import (
    Generator,
    derive_seed,
    get_generator,
    registered_generators,
    resolve_variables,
)
from compactbench.dsl.models import (
    DifficultyLevel,
    DifficultyPolicy,
    EvaluationItemTemplate,
    GroundTruthTemplate,
    TemplateDefinition,
    TemplateTurnRole,
    TranscriptTemplate,
    TurnTemplate,
    VariableDeclaration,
)
from compactbench.dsl.parser import (
    load_suite,
    parse_template_file,
    parse_template_string,
)
from compactbench.dsl.substitution import extract_references, substitute
from compactbench.dsl.validator import validate_template

__all__ = [
    "DifficultyLevel",
    "DifficultyPolicy",
    "EvaluationItemTemplate",
    "Generator",
    "GroundTruthTemplate",
    "TemplateDefinition",
    "TemplateError",
    "TemplateParseError",
    "TemplateTurnRole",
    "TemplateValidationError",
    "TranscriptTemplate",
    "TurnTemplate",
    "UnknownGeneratorError",
    "UnresolvedReferenceError",
    "VariableDeclaration",
    "derive_seed",
    "extract_references",
    "get_generator",
    "load_suite",
    "parse_template_file",
    "parse_template_string",
    "registered_generators",
    "resolve_variables",
    "substitute",
    "validate_template",
]
