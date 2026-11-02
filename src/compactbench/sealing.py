"""Sealed secrets: encrypt to a public key so only the holder of the private key can read it.

Ranked evaluation uses this twice:

- **Submitter keys.** A submitter seals their own provider API key to the
  season's public key (``compactbench keys seal``) and puts the result in their
  submission. Only the evaluation proxy, which holds the season's private key,
  can open it, and the key never reaches the sandboxed method.
- **Private traces.** Evaluation traces hold the hidden cases, so they're sealed
  to the maintainers' public key before they leave the runner.

The scheme is an ECIES-style sealed box: an ephemeral X25519 key agreement,
HKDF-SHA256, and AES-256-GCM — all available in WebCrypto too, so other
implementations can seal with exactly the same scheme. A ``context`` string is bound into the key
derivation, so a sealed value only opens for the purpose it was made for — a key
sealed for one submission can't be pasted into another.
"""

from __future__ import annotations

import base64
import os

PREFIX = "cbseal1:"
_INFO = b"compactbench-seal-v1"


class SealingError(ValueError):
    """A sealed value was malformed, or didn't open with this key and context."""


def _require_crypto() -> None:
    try:
        import cryptography  # noqa: F401  # pyright: ignore[reportUnusedImport]
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SealingError(
            "sealing needs the 'cryptography' package: pip install 'compactbench[ranked]'"
        ) from exc


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str, *, length: int | None = None, what: str = "value") -> bytes:
    try:
        data = base64.urlsafe_b64decode(text.strip() + "=" * (-len(text.strip()) % 4))
    except (ValueError, TypeError) as exc:
        raise SealingError(f"{what} is not valid base64") from exc
    if length is not None and len(data) != length:
        raise SealingError(f"{what} must be {length} bytes")
    return data


def _derive(shared: bytes, ephemeral: bytes, recipient: bytes, context: str) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    info = _INFO + ephemeral + recipient + context.encode("utf-8")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(shared)


def generate_keypair() -> tuple[str, str]:
    """A new ``(private_key, public_key)`` pair, both base64url text."""
    _require_crypto()
    from cryptography.hazmat.primitives import serialization as ser
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    private = X25519PrivateKey.generate()
    raw_private = private.private_bytes(ser.Encoding.Raw, ser.PrivateFormat.Raw, ser.NoEncryption())
    raw_public = private.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
    return _b64(raw_private), _b64(raw_public)


def public_key_of(private_key: str) -> str:
    """The public key that goes with ``private_key``."""
    _require_crypto()
    from cryptography.hazmat.primitives import serialization as ser
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    private = X25519PrivateKey.from_private_bytes(
        _unb64(private_key, length=32, what="private key")
    )
    return _b64(private.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw))


def seal(public_key: str, plaintext: bytes, *, context: str) -> str:
    """Encrypt ``plaintext`` to ``public_key``; it only opens with the same ``context``."""
    _require_crypto()
    from cryptography.hazmat.primitives import serialization as ser
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    recipient = _unb64(public_key, length=32, what="public key")
    ephemeral = X25519PrivateKey.generate()
    ephemeral_public = ephemeral.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
    shared = ephemeral.exchange(X25519PublicKey.from_public_bytes(recipient))
    key = _derive(shared, ephemeral_public, recipient, context)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return PREFIX + _b64(ephemeral_public + nonce + ciphertext)


def open_sealed(private_key: str, sealed: str, *, context: str) -> bytes:
    """Decrypt a value from :func:`seal`. Raises :class:`SealingError` on any mismatch."""
    _require_crypto()
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    sealed = sealed.strip()
    if not sealed.startswith(PREFIX):
        raise SealingError(f"sealed values start with {PREFIX!r}")
    blob = _unb64(sealed[len(PREFIX) :], what="sealed value")
    if len(blob) < 32 + 12 + 16:
        raise SealingError("sealed value is too short")
    ephemeral_public, nonce, ciphertext = blob[:32], blob[32:44], blob[44:]
    recipient = _unb64(public_key_of(private_key), what="public key")
    private = X25519PrivateKey.from_private_bytes(
        _unb64(private_key, length=32, what="private key")
    )
    shared = private.exchange(X25519PublicKey.from_public_bytes(ephemeral_public))
    key = _derive(shared, ephemeral_public, recipient, context)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise SealingError("sealed value doesn't open with this key and context") from exc


def key_context(season: str, submission: str) -> str:
    """The context a submitter's API key is sealed under, e.g. ``key:s1:alice/ledger``."""
    return f"key:{season}:{submission}"
