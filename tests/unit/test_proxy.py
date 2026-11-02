"""The ranked evaluation's model proxy."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest

from compactbench.proxy import ProxyConfig, Upstream, network_reach, serve, usage_from

pytestmark = pytest.mark.unit


class _Upstream(BaseHTTPRequestHandler):
    seen: ClassVar[list[dict[str, Any]]] = []

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Upstream.seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
        reply = json.dumps(
            {
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 120, "output_tokens": 30},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)


@pytest.fixture
def upstream() -> Iterator[str]:
    _Upstream.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _proxy(upstream: str, tmp_path: Path, **overrides: Any) -> tuple[str, Any]:
    config = ProxyConfig(
        keys={"anthropic": "real-key"},
        models=frozenset({"claude-haiku-5-5"}),
        log_path=tmp_path / "calls.jsonl",
        routes={"anthropic": Upstream(upstream, "x-api-key", frozenset({"/v1/messages"}))},
        **overrides,
    )
    proxy = serve(config, host="127.0.0.1", port=0)
    return f"http://127.0.0.1:{proxy.server_address[1]}", proxy


def _call(base: str, body: dict[str, Any], path: str = "/anthropic/v1/messages") -> httpx.Response:
    return httpx.post(base + path, json=body, headers={"x-api-key": "sandbox-dummy"}, timeout=10)


def test_forwards_with_the_real_key_and_counts_usage(upstream: str, tmp_path: Path) -> None:
    base, proxy = _proxy(upstream, tmp_path)
    try:
        response = _call(
            base,
            {
                "model": "claude-haiku-5-5",
                "messages": [{"role": "user", "content": "SECRET CASE TEXT"}],
            },
        )
        assert response.status_code == 200
        sent = _Upstream.seen[0]
        assert sent["path"] == "/v1/messages"
        assert sent["headers"]["x-api-key"] == "real-key"
        assert "sandbox-dummy" not in json.dumps(sent["headers"])
        assert proxy.stats.input_tokens == 120
        assert proxy.stats.output_tokens == 30
        log = (tmp_path / "calls.jsonl").read_text()
        assert "SECRET CASE TEXT" not in log
        assert json.loads(log.splitlines()[0])["model"] == "claude-haiku-5-5"
    finally:
        proxy.shutdown()
        proxy.server_close()


@pytest.mark.parametrize(
    ("body", "path", "status"),
    [
        ({"model": "claude-opus-5-5"}, "/anthropic/v1/messages", 403),
        ({"model": "claude-haiku-5-5", "stream": True}, "/anthropic/v1/messages", 400),
        ({"model": "claude-haiku-5-5"}, "/anthropic/v1/files", 404),
        ({"model": "claude-haiku-5-5"}, "/anthropic/v1/messages/batches", 404),
        ({"model": "claude-haiku-5-5"}, "/anthropic/v1/messages/../files", 404),
        (
            {"model": "claude-haiku-5-5", "tools": [{"type": "web_fetch_20260209", "name": "f"}]},
            "/anthropic/v1/messages",
            403,
        ),
        (
            {
                "model": "claude-haiku-5-5",
                "mcp_servers": [{"type": "url", "url": "https://x.test"}],
            },
            "/anthropic/v1/messages",
            403,
        ),
        (
            {
                "model": "claude-haiku-5-5",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "url", "url": "https://x.test/?q=1"},
                            }
                        ],
                    }
                ],
            },
            "/anthropic/v1/messages",
            403,
        ),
        ({"model": "gpt-5"}, "/openai/v1/chat/completions", 404),
    ],
)
def test_refuses_what_the_run_did_not_declare(
    upstream: str, tmp_path: Path, body: dict[str, Any], path: str, status: int
) -> None:
    base, proxy = _proxy(upstream, tmp_path)
    try:
        assert _call(base, body, path).status_code == status
        assert _Upstream.seen == []
    finally:
        proxy.shutdown()
        proxy.server_close()


def test_stops_at_the_token_cap(upstream: str, tmp_path: Path) -> None:
    base, proxy = _proxy(upstream, tmp_path, max_tokens=100)
    try:
        assert _call(base, {"model": "claude-haiku-5-5"}).status_code == 200
        # 150 tokens used, cap is 100: the next call is refused without reaching upstream.
        assert _call(base, {"model": "claude-haiku-5-5"}).status_code == 403
        assert len(_Upstream.seen) == 1
    finally:
        proxy.shutdown()
        proxy.server_close()


def test_health_check(upstream: str, tmp_path: Path) -> None:
    base, proxy = _proxy(upstream, tmp_path)
    try:
        assert httpx.get(base + "/healthz", timeout=5).status_code == 200
    finally:
        proxy.shutdown()
        proxy.server_close()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            {"usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 90}},
            (100, 5),
        ),
        ({"usage": {"prompt_tokens": 7, "completion_tokens": 3}}, (7, 3)),
        (
            {
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "iterations": [{"input_tokens": 50, "output_tokens": 9}],
                }
            },
            (50, 9),
        ),
        (
            {
                "usageMetadata": {
                    "promptTokenCount": 11,
                    "candidatesTokenCount": 4,
                    "thoughtsTokenCount": 6,
                }
            },
            (11, 10),
        ),
        ([], (0, 0)),
    ],
)
def test_usage_extraction(body: Any, expected: tuple[int, int]) -> None:
    assert usage_from(body) == expected


def test_client_side_tools_and_plain_text_links_are_allowed() -> None:
    body = {
        "tools": [{"name": "lookup", "input_schema": {"type": "object"}}, {"type": "function"}],
        "messages": [{"role": "user", "content": "see https://example.com in plain text"}],
    }
    assert network_reach(body) is None


@pytest.mark.parametrize(
    "body",
    [
        {"tools": [{"type": "web_search"}]},
        {"input": [{"content": [{"type": "input_image", "image_url": "https://x.test/a.png"}]}]},
        {"web_search_options": {}},
    ],
)
def test_openai_style_network_features_are_refused(body: dict[str, Any]) -> None:
    assert network_reach(body) is not None


def _resolves_to(monkeypatch: pytest.MonkeyPatch, *addresses: str) -> None:
    import socket

    def fake(*_args: object, **_kwargs: object) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in addresses]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


def test_custom_endpoint_allows_one_public_https_host(monkeypatch: pytest.MonkeyPatch) -> None:
    from compactbench.proxy import custom_upstream

    _resolves_to(monkeypatch, "93.184.216.34")
    upstream = custom_upstream("https://models.example.com/v1/")
    assert upstream.base_url == "https://models.example.com"
    assert upstream.allows("/v1/chat/completions")
    assert not upstream.allows("/v1/files")
    assert upstream.public_only


@pytest.mark.parametrize(
    ("url", "addresses"),
    [
        ("http://models.example.com/v1", ("93.184.216.34",)),  # not https
        ("https://user:pw@models.example.com/v1", ("93.184.216.34",)),  # credentials
        ("https://internal.example.com/v1", ("10.0.0.5",)),  # private
        ("https://meta.example.com/v1", ("169.254.169.254",)),  # cloud metadata
        ("https://loop.example.com/v1", ("127.0.0.1",)),  # loopback
        ("https://mixed.example.com/v1", ("93.184.216.34", "192.168.1.2")),  # any private
    ],
)
def test_custom_endpoint_refuses_unsafe_targets(
    monkeypatch: pytest.MonkeyPatch, url: str, addresses: tuple[str, ...]
) -> None:
    from compactbench.proxy import EndpointError, custom_upstream

    _resolves_to(monkeypatch, *addresses)
    with pytest.raises(EndpointError):
        custom_upstream(url)
