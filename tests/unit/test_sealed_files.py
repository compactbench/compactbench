"""Sealing whole files (the method image between jobs), streamed and tamper-evident."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

import pytest

from compactbench.sealing import SealingError, generate_keypair, open_sealed_file, seal_file

pytestmark = pytest.mark.unit


def test_a_large_file_round_trips(tmp_path: Path) -> None:
    private, public = generate_keypair()
    data = os.urandom(3 * (1 << 20) + 12345)  # several chunks, not a multiple of one
    (tmp_path / "image").write_bytes(data)
    seal_file(public, tmp_path / "image", tmp_path / "sealed", context="image:s1:abc")
    assert data[:4096] not in (tmp_path / "sealed").read_bytes()
    open_sealed_file(private, tmp_path / "sealed", tmp_path / "back", context="image:s1:abc")
    assert (tmp_path / "back").read_bytes() == data


@pytest.mark.parametrize("change", ["context", "key", "flip", "truncate"])
def test_a_wrong_key_context_or_altered_file_is_refused(tmp_path: Path, change: str) -> None:
    private, public = generate_keypair()
    (tmp_path / "image").write_bytes(os.urandom(200_000))
    seal_file(public, tmp_path / "image", tmp_path / "sealed", context="image:s1:abc")
    context = "image:s1:abc"
    if change == "context":
        context = "image:s1:other"
    elif change == "key":
        private, _ = generate_keypair()
    elif change == "flip":
        blob = bytearray((tmp_path / "sealed").read_bytes())
        blob[len(blob) // 2] ^= 1
        (tmp_path / "sealed").write_bytes(bytes(blob))
    else:
        blob = (tmp_path / "sealed").read_bytes()
        (tmp_path / "sealed").write_bytes(blob[:-100])
    with pytest.raises(SealingError):
        open_sealed_file(private, tmp_path / "sealed", tmp_path / "back", context=context)
    assert not (tmp_path / "back").exists(), "nothing unverified is left behind"


def _image_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "ranked" / "image.py"
    spec = importlib.util.spec_from_file_location("ranked_image", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_image_script_seals_in_build_and_opens_in_evaluate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = _image_script()
    private, public = generate_keypair()
    season = Path(__file__).resolve().parents[2] / "seasons" / "s1.yaml"
    text = season.read_text(encoding="utf-8")
    lines = [
        f'public_key: "{public}"' if line.startswith("public_key:") else line
        for line in text.splitlines()
    ]
    (tmp_path / "s1.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "img.tar.gz").write_bytes(b"pretend image with method.py inside")
    args = ["--season", str(tmp_path / "s1.yaml"), "--id", "abcdefghijkl1234"]
    assert image.main(["seal", str(tmp_path / "img.tar.gz"), str(tmp_path / "s"), *args]) == 0
    monkeypatch.delenv("COMPACTBENCH_SEASON_PRIVATE_KEY", raising=False)
    assert image.main(["open", str(tmp_path / "s"), str(tmp_path / "out"), *args]) == 1
    monkeypatch.setenv("COMPACTBENCH_SEASON_PRIVATE_KEY", private)
    other = ["--season", str(tmp_path / "s1.yaml"), "--id", "zzzzzzzzzzzz9999"]
    assert image.main(["open", str(tmp_path / "s"), str(tmp_path / "out"), *other]) == 1
    monkeypatch.setenv("COMPACTBENCH_SEASON_PRIVATE_KEY", private)
    assert image.main(["open", str(tmp_path / "s"), str(tmp_path / "out"), *args]) == 0
    assert (tmp_path / "out").read_bytes() == b"pretend image with method.py inside"
