"""Exception hierarchy for template DSL operations."""

from __future__ import annotations


class TemplateError(Exception):
    """Base exception for anything DSL-related."""


class TemplateParseError(TemplateError):
    """YAML structure does not match the template DSL shape."""


class TemplateValidationError(TemplateError):
    """Template is structurally valid but has a semantic error."""


class UnknownGeneratorError(TemplateError):
    """A variable references a generator that is not registered."""


class UnresolvedReferenceError(TemplateError):
    """A ``{{reference}}`` in the template cannot be resolved from the bindings."""
