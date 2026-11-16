"""The evaluation workflow's calls to the site: keeping a finished run's files privately."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ranked" / "site.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ranked_site", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


site = _load()


@pytest.fixture
def evaluation(tmp_path: Path) -> Path:
    for name in ("traces.sealed", "results.sealed", "commitment.json", "results.jsonl"):
        (tmp_path / name).write_bytes(name.encode())
    (tmp_path / "bundle.json").write_text("{}")  # never archived
    return tmp_path


def _fake_put(monkeypatch: pytest.MonkeyPatch, statuses: list[int]) -> list[tuple[str, bytes]]:
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(site, "_oidc_token", lambda: "token")

    def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(site.time, "sleep", no_sleep)

    def put(url: str, *, headers: dict[str, str], content: bytes, **_: Any) -> httpx.Response:
        assert headers == {"Authorization": "Bearer token"}
        sent.append((url, content))
        status = statuses.pop(0) if statuses else 200
        return httpx.Response(status, request=httpx.Request("PUT", url))

    monkeypatch.setattr(site.httpx, "put", put)
    return sent


def test_archive_sends_only_the_run_files_present(
    monkeypatch: pytest.MonkeyPatch, evaluation: Path
) -> None:
    sent = _fake_put(monkeypatch, [])
    assert site.archive("abcdefghijkl", evaluation) == 0
    names = [url.rsplit("/", 1)[1] for url, _ in sent]
    assert names == ["results.sealed", "traces.sealed", "commitment.json", "results.jsonl"]
    assert all(url.startswith(f"{site.SITE}/api/internal/archive/abcdefghijkl/") for url, _ in sent)
    assert (
        dict((url.rsplit("/", 1)[1], body) for url, body in sent)["traces.sealed"]
        == b"traces.sealed"
    )


def test_archive_retries_then_reports_without_details(
    monkeypatch: pytest.MonkeyPatch, evaluation: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # results.sealed fails all three tries; traces.sealed succeeds on its second.
    sent = _fake_put(monkeypatch, [503, 503, 503, 500, 200])
    assert site.archive("abcdefghijkl", evaluation) == 1
    assert len(sent) == 3 + 2 + 1 + 1
    assert "::warning::results.sealed wasn't archived (HTTP 503)" in capsys.readouterr().out


def test_main_archive_exit_code(monkeypatch: pytest.MonkeyPatch, evaluation: Path) -> None:
    _fake_put(monkeypatch, [])
    assert site.main(["site.py", "archive", "abcdefghijkl", str(evaluation)]) == 0
    assert site.main(["site.py", "archive", "../etc", str(evaluation)]) == 2
