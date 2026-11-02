"""Sealed secrets for ranked evaluation."""

from __future__ import annotations

import pytest

from compactbench.sealing import (
    PREFIX,
    SealingError,
    generate_keypair,
    key_context,
    open_sealed,
    public_key_of,
    seal,
)

pytestmark = pytest.mark.unit


def test_round_trip() -> None:
    private, public = generate_keypair()
    sealed = seal(public, b"sk-test-123", context="key:s1:alice/ledger")
    assert sealed.startswith(PREFIX)
    assert b"sk-test-123" not in sealed.encode()
    assert open_sealed(private, sealed, context="key:s1:alice/ledger") == b"sk-test-123"


def test_public_key_is_derived_from_the_private_key() -> None:
    private, public = generate_keypair()
    assert public_key_of(private) == public


def test_sealing_twice_gives_different_ciphertexts() -> None:
    _, public = generate_keypair()
    assert seal(public, b"x", context="c") != seal(public, b"x", context="c")


def test_a_key_sealed_for_one_submission_does_not_open_for_another() -> None:
    private, public = generate_keypair()
    sealed = seal(public, b"secret", context=key_context("s1", "alice/ledger"))
    with pytest.raises(SealingError):
        open_sealed(private, sealed, context=key_context("s1", "mallory/copycat"))


def test_wrong_private_key_fails() -> None:
    _, public = generate_keypair()
    other, _ = generate_keypair()
    with pytest.raises(SealingError):
        open_sealed(other, seal(public, b"secret", context="c"), context="c")


@pytest.mark.parametrize("bad", ["", "nope", PREFIX + "!!!", PREFIX + "AAAA"])
def test_malformed_values_are_rejected(bad: str) -> None:
    private, _ = generate_keypair()
    with pytest.raises(SealingError):
        open_sealed(private, bad, context="c")


def test_tampering_is_detected() -> None:
    private, public = generate_keypair()
    sealed = seal(public, b"secret", context="c")
    flipped = sealed[:-2] + ("A" if sealed[-2] != "A" else "B") + sealed[-1]
    with pytest.raises(SealingError):
        open_sealed(private, flipped, context="c")


# Sealed by an independent WebCrypto implementation with a test-only keypair. If either
# implementation changes, this stops opening.
_FIXTURE_PRIVATE = "eAz-9g9f5SlEWgw3afejhSm7fGbuiCBtOrzVIKqrAXE"
_FIXTURE_SEALED_BY_WORKER = "cbseal1:ccwHv_fzcmYmhsXMiUhT6_MH3Z5n8Mk6JR0_pynthgyozAYVWFIbHm5YqY5Z6ZrKOzPo0CpH904cPs2d7HYMI_6aw5wFhiXqF_kz4N8f"


def test_opens_a_value_sealed_by_webcrypto() -> None:
    assert (
        open_sealed(_FIXTURE_PRIVATE, _FIXTURE_SEALED_BY_WORKER, context="key:s1:fixture000001")
        == b"sk-interop-fixture"
    )
