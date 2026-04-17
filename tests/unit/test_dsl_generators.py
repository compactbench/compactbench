"""Determinism and coverage tests for seeded generators."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from compactbench.dsl import (
    UnknownGeneratorError,
    VariableDeclaration,
    derive_seed,
    get_generator,
    registered_generators,
    resolve_variables,
)

pytestmark = pytest.mark.unit


def test_derive_seed_is_deterministic() -> None:
    assert derive_seed(42, "foo") == derive_seed(42, "foo")


def test_derive_seed_differs_by_name() -> None:
    assert derive_seed(42, "foo") != derive_seed(42, "bar")


def test_derive_seed_differs_by_base_seed() -> None:
    assert derive_seed(1, "foo") != derive_seed(2, "foo")


@given(seed=st.integers(min_value=0, max_value=2**63 - 1), name=st.text(min_size=1, max_size=20))
def test_derive_seed_is_deterministic_over_any_input(seed: int, name: str) -> None:
    assert derive_seed(seed, name) == derive_seed(seed, name)


def test_registered_generators_includes_required_set() -> None:
    required = {
        "person_name",
        "action_phrase",
        "project_noun",
        "org_name",
        "date_iso",
        "amount_usd",
        "product_sku",
    }
    assert required.issubset(set(registered_generators()))


@pytest.mark.parametrize(
    "generator_name",
    [
        "person_name",
        "action_phrase",
        "project_noun",
        "org_name",
        "date_iso",
        "amount_usd",
        "product_sku",
    ],
)
def test_each_generator_is_deterministic(generator_name: str) -> None:
    gen = get_generator(generator_name)
    assert gen.generate(12345) == gen.generate(12345)


@pytest.mark.parametrize(
    "generator_name",
    [
        "person_name",
        "action_phrase",
        "project_noun",
        "org_name",
        "date_iso",
        "amount_usd",
        "product_sku",
    ],
)
def test_each_generator_returns_nonempty_string(generator_name: str) -> None:
    gen = get_generator(generator_name)
    output = gen.generate(7)
    assert isinstance(output, str)
    assert output


def test_date_generator_returns_iso_format() -> None:
    gen = get_generator("date_iso")
    out = gen.generate(9)
    assert len(out) == 10
    assert out[4] == "-"
    assert out[7] == "-"


def test_amount_generator_starts_with_dollar_sign() -> None:
    gen = get_generator("amount_usd")
    out = gen.generate(9)
    assert out.startswith("$")


def test_sku_generator_has_expected_shape() -> None:
    gen = get_generator("product_sku")
    out = gen.generate(9)
    assert "-" in out
    prefix, suffix = out.split("-")
    assert prefix in {"SKU", "PRD", "ITEM", "ART"}
    assert len(suffix) >= 5


def test_get_generator_raises_on_unknown() -> None:
    with pytest.raises(UnknownGeneratorError):
        get_generator("not_a_real_generator")


def test_resolve_variables_is_deterministic() -> None:
    decls = [
        VariableDeclaration(name="a", generator="person_name"),
        VariableDeclaration(name="b", generator="project_noun"),
    ]
    assert resolve_variables(decls, 999) == resolve_variables(decls, 999)


def test_resolve_variables_differs_by_seed() -> None:
    decls = [VariableDeclaration(name="a", generator="person_name")]
    # Two seeds we know index to different positions in the 36-name lexicon.
    a = resolve_variables(decls, 1)
    b = resolve_variables(decls, 100)
    assert a != b


def test_resolve_variables_uses_declared_names_as_keys() -> None:
    decls = [
        VariableDeclaration(name="alpha", generator="person_name"),
        VariableDeclaration(name="beta", generator="project_noun"),
    ]
    resolved = resolve_variables(decls, 42)
    assert set(resolved.keys()) == {"alpha", "beta"}


def test_resolve_variables_raises_on_unknown_generator() -> None:
    decls = [VariableDeclaration(name="a", generator="ghost_generator")]
    with pytest.raises(UnknownGeneratorError):
        resolve_variables(decls, 1)


def test_reordering_variables_does_not_change_unchanged_ones() -> None:
    """Core determinism guarantee: adding/reordering variables cannot shift
    the output of unchanged variables."""
    first = [
        VariableDeclaration(name="stable", generator="person_name"),
        VariableDeclaration(name="other", generator="project_noun"),
    ]
    second = [
        VariableDeclaration(name="other", generator="project_noun"),
        VariableDeclaration(name="stable", generator="person_name"),
        VariableDeclaration(name="new", generator="org_name"),
    ]
    r1 = resolve_variables(first, 42)
    r2 = resolve_variables(second, 42)
    assert r1["stable"] == r2["stable"]
    assert r1["other"] == r2["other"]
