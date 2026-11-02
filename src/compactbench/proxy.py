"""Model proxy for ranked evaluation: the only network a sandboxed method gets.

A submitted method runs in a container whose one network peer is this proxy.
The method's SDK is pointed at the proxy (``ANTHROPIC_BASE_URL`` and friends)
with a dummy key. The proxy:

- holds the real provider keys and swaps them in, so the method never sees one;
- forwards only model-call endpoints of known providers, and only for the
  models the submission declared;
- refuses requests that would make the provider reach the internet on the
  method's behalf — server-side tools (web search and fetch, code execution),
  MCP servers, and images or documents given by URL — since those would be
  network access around the sandbox;
- refuses streaming, so every response's token usage can be counted;
- stops forwarding once the run's request or token cap is reached;
- logs every call's route, model, status and token counts — never bodies, which
  hold the hidden cases.

It is deliberately small: the standard library's threading HTTP server plus
``httpx`` for the upstream call.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

MAX_BODY_BYTES = 32 * 1024 * 1024
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
        "accept-encoding",
        "content-encoding",
    }
)
_CREDENTIAL_HEADERS = frozenset({"authorization", "x-api-key", "x-goog-api-key", "api-key"})


@dataclass(frozen=True)
class Upstream:
    """A provider the proxy can forward to."""

    base_url: str
    auth: str
    """``"bearer"`` (Authorization header) or the name of the header carrying the key."""
    paths: frozenset[str]
    """Exact paths allowed. Anything else (files, batches, admin…) is refused."""
    pattern: re.Pattern[str] | None = None
    """Extra allowed paths, for providers that put the model in the path."""
    public_only: bool = False
    """Re-check before every call that the host resolves only to public addresses
    (submitter-supplied endpoints, so they can't point the proxy at internal ones)."""

    def allows(self, path: str) -> bool:
        return path in self.paths or bool(self.pattern and self.pattern.fullmatch(path))


ROUTES: dict[str, Upstream] = {
    "anthropic": Upstream(
        "https://api.anthropic.com",
        "x-api-key",
        frozenset({"/v1/messages", "/v1/messages/count_tokens", "/v1/models"}),
    ),
    "openai": Upstream(
        "https://api.openai.com",
        "bearer",
        frozenset({"/v1/chat/completions", "/v1/responses", "/v1/models"}),
    ),
    "groq": Upstream(
        "https://api.groq.com",
        "bearer",
        frozenset({"/openai/v1/chat/completions", "/openai/v1/models"}),
    ),
    "google": Upstream(
        "https://generativelanguage.googleapis.com",
        "x-goog-api-key",
        frozenset(),
        re.compile(r"/v1beta/models/[A-Za-z0-9._-]+:(generateContent|countTokens)"),
    ),
    "openrouter": Upstream(
        "https://openrouter.ai", "bearer", frozenset({"/api/v1/chat/completions"})
    ),
    "deepseek": Upstream("https://api.deepseek.com", "bearer", frozenset({"/v1/chat/completions"})),
    "mistral": Upstream("https://api.mistral.ai", "bearer", frozenset({"/v1/chat/completions"})),
    "together": Upstream("https://api.together.xyz", "bearer", frozenset({"/v1/chat/completions"})),
    "fireworks": Upstream(
        "https://api.fireworks.ai", "bearer", frozenset({"/inference/v1/chat/completions"})
    ),
    "xai": Upstream("https://api.x.ai", "bearer", frozenset({"/v1/chat/completions"})),
    "gemini": Upstream(
        "https://generativelanguage.googleapis.com",
        "bearer",
        frozenset({"/v1beta/openai/chat/completions"}),
    ),
}


class EndpointError(ValueError):
    """A submitter-supplied endpoint that the proxy won't forward to."""


def custom_upstream(url: str) -> Upstream:
    """An :class:`Upstream` for a submitter's own OpenAI-compatible endpoint.

    ``url`` is the base URL their SDK would use (``https://host/v1``). Only that host,
    over HTTPS, and only its chat-completions path are allowed.
    """
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or not parts.hostname:
        raise EndpointError("a custom endpoint must be an https:// URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise EndpointError("a custom endpoint URL can't carry credentials, a query or a fragment")
    ensure_public_host(parts.hostname)
    base = f"https://{parts.netloc}"
    path = parts.path.rstrip("/")
    return Upstream(base, "bearer", frozenset({f"{path}/chat/completions"}), public_only=True)


def ensure_public_host(host: str) -> None:
    """Raise unless every address ``host`` resolves to is publicly routable."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise EndpointError(f"can't resolve {host}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_multicast:
            raise EndpointError(f"{host} resolves to a non-public address")


# Request fields that make the provider act on the network for the caller.
_NETWORK_FIELDS = frozenset({"mcp_servers", "container", "web_search_options", "plugins"})
# Tool types that run on the caller's side; anything else is a server-side tool.
_CLIENT_TOOL_TYPES = frozenset({"custom", "function"})


def network_reach(payload: Any) -> str | None:
    """Why ``payload`` would make the provider reach the network, or ``None``.

    Checks the whole body: server-side tools, MCP servers and containers, and any
    content given by URL (an image or document the provider would fetch).
    """
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(cast("list[Any]", node))
            continue
        if not isinstance(node, dict):
            continue
        data = cast("dict[str, Any]", node)
        for key, value in data.items():
            # Presence is enough: an empty `web_search_options: {}` still turns search on.
            if key in _NETWORK_FIELDS and value is not None:
                return f"{key!r} isn't allowed in ranked runs"
            if key in {"url", "image_url", "file_url"} and _is_remote(value):
                return "content given by URL isn't allowed in ranked runs"
            if key == "tools" and isinstance(value, list):
                for tool in cast("list[Any]", value):
                    kind = (
                        cast("dict[str, Any]", tool).get("type") if isinstance(tool, dict) else None
                    )
                    if kind is not None and kind not in _CLIENT_TOOL_TYPES:
                        return f"server-side tool {str(kind)[:60]!r} isn't allowed in ranked runs"
            stack.append(value)
    return None


def _is_remote(value: Any) -> bool:
    if isinstance(value, dict):
        value = cast("dict[str, Any]", value).get("url")
    return isinstance(value, str) and value.lower().startswith(("http:", "https:", "//"))


@dataclass
class ProxyConfig:
    keys: dict[str, str]
    """Route name → real API key. Routes without a key are refused."""
    models: frozenset[str] = frozenset()
    """Models the method may call; empty allows any."""
    max_requests: int = 10_000
    max_tokens: int = 50_000_000
    """Cap on input plus output tokens across the run."""
    log_path: Path | None = None
    routes: dict[str, Upstream] = field(default_factory=lambda: dict(ROUTES))
    timeout_seconds: float = 600.0


@dataclass
class ProxyStats:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    refused: int = 0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def usage_from(body: Any) -> tuple[int, int]:
    """``(input, output)`` tokens reported in a provider response body."""
    if not isinstance(body, dict):
        return 0, 0
    data = cast("dict[str, Any]", body)
    usage = data.get("usage")
    if isinstance(usage, dict):
        u = cast("dict[str, Any]", usage)
        iterations = u.get("iterations")
        if isinstance(iterations, list) and iterations:
            # Anthropic compaction reports its real counts per iteration.
            items = [
                cast("dict[str, Any]", i)
                for i in cast("list[Any]", iterations)
                if isinstance(i, dict)
            ]
            return (
                sum(_int(i.get("input_tokens")) for i in items),
                sum(_int(i.get("output_tokens")) for i in items),
            )
        prompt = (
            _int(u.get("input_tokens"))
            + _int(u.get("cache_creation_input_tokens"))
            + _int(u.get("cache_read_input_tokens"))
            + _int(u.get("prompt_tokens"))
        )
        return prompt, _int(u.get("output_tokens")) + _int(u.get("completion_tokens"))
    meta = data.get("usageMetadata")
    if isinstance(meta, dict):
        m = cast("dict[str, Any]", meta)
        return (
            _int(m.get("promptTokenCount")),
            _int(m.get("candidatesTokenCount")) + _int(m.get("thoughtsTokenCount")),
        )
    return 0, 0


def _int(value: Any) -> int:
    return value if isinstance(value, int) and value > 0 else 0


class ModelProxy(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], config: ProxyConfig) -> None:
        super().__init__(address, _Handler)
        self.config = config
        self.stats = ProxyStats()
        self.lock = threading.Lock()
        self.client = httpx.Client(timeout=config.timeout_seconds, follow_redirects=False)
        self._log = config.log_path.open("a", encoding="utf-8") if config.log_path else None

    def record(self, entry: dict[str, Any]) -> None:
        if self._log is None:
            return
        with self.lock:
            self._log.write(json.dumps(entry, sort_keys=True) + "\n")
            self._log.flush()

    def server_close(self) -> None:
        super().server_close()
        self.client.close()
        if self._log is not None:
            self._log.close()


class _Handler(BaseHTTPRequestHandler):
    server: ModelProxy  # pyright: ignore[reportIncompatibleVariableOverride]
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        # The structured call log replaces the default access log on stderr.
        return

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._reply(200, {"ok": True})
            return
        self._forward("GET")

    def do_POST(self) -> None:
        self._forward("POST")

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _refuse(self, status: int, message: str, route: str = "", model: str = "") -> None:
        with self.server.lock:
            self.server.stats.refused += 1
        self.server.record(
            {
                "ts": time.time(),
                "route": route,
                "model": model,
                "status": status,
                "refused": message,
            }
        )
        self._reply(status, {"error": {"type": "compactbench_proxy", "message": message}})

    def _forward(self, method: str) -> None:
        server = self.server
        config = server.config
        parts = urlsplit(self.path)
        route, _, rest = parts.path.lstrip("/").partition("/")
        upstream = config.routes.get(route)
        path = "/" + rest
        if upstream is None or route not in config.keys:
            self._refuse(404, f"unknown route {route!r}")
            return
        if not upstream.allows(path):
            self._refuse(404, f"{route} path not allowed: {path[:200]}", route)
            return
        if upstream.public_only:
            try:
                ensure_public_host(urlsplit(upstream.base_url).hostname or "")
            except EndpointError as exc:
                self._refuse(403, str(exc), route)
                return
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            self._refuse(411, "send a Content-Length, not a chunked body", route)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self._refuse(413, "request body too large", route)
            return
        raw = self.rfile.read(length) if length else b""
        payload: Any = None
        if raw:
            try:
                payload = json.loads(raw)
            except ValueError:
                self._refuse(400, "request body must be JSON", route)
                return
        model = _model_of(payload, path)
        if config.models and method == "POST" and model not in config.models:
            self._refuse(403, f"model {model!r} is not declared for this run", route, model)
            return
        if isinstance(payload, dict) and cast("dict[str, Any]", payload).get("stream") is True:
            self._refuse(400, "streaming isn't supported in ranked runs", route, model)
            return
        reach = network_reach(payload)
        if reach is not None:
            self._refuse(403, reach, route, model)
            return
        with server.lock:
            stats = server.stats
            if stats.requests >= config.max_requests or stats.tokens >= config.max_tokens:
                exhausted = True
            else:
                exhausted = False
                stats.requests += 1
        if exhausted:
            self._refuse(403, "this run's request or token cap is used up", route, model)
            return

        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in _HOP_BY_HOP and k.lower() not in _CREDENTIAL_HEADERS
        }
        key = config.keys[route]
        if not key:
            pass  # a submitter's own endpoint that takes no key
        elif upstream.auth == "bearer":
            headers["Authorization"] = f"Bearer {key}"
        else:
            headers[upstream.auth] = key
        query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.lower() != "key"])
        url = upstream.base_url + path + (f"?{query}" if query else "")
        started = time.perf_counter()
        try:
            response = server.client.request(method, url, content=raw or None, headers=headers)
        except httpx.HTTPError as exc:
            self._refuse(502, f"upstream error: {type(exc).__name__}", route, model)
            return
        body = response.content
        try:
            input_tokens, output_tokens = usage_from(response.json())
        except ValueError:
            input_tokens, output_tokens = 0, 0
        with server.lock:
            server.stats.input_tokens += input_tokens
            server.stats.output_tokens += output_tokens
        server.record(
            {
                "ts": time.time(),
                "route": route,
                "path": path,
                "model": model,
                "status": response.status_code,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "ms": int((time.perf_counter() - started) * 1000),
            }
        )
        self.send_response(response.status_code)
        for k, v in response.headers.items():
            if k.lower() not in _HOP_BY_HOP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _model_of(payload: Any, path: str) -> str:
    if isinstance(payload, dict):
        model = cast("dict[str, Any]", payload).get("model")
        if isinstance(model, str):
            return model
    # Google puts the model in the path: /v1beta/models/<model>:generateContent
    if "/models/" in path:
        return path.split("/models/", 1)[1].split(":", 1)[0]
    return ""


def serve(config: ProxyConfig, host: str = "0.0.0.0", port: int = 8080) -> ModelProxy:
    """Start the proxy on a background thread and return it (``shutdown()`` to stop)."""
    proxy = ModelProxy((host, port), config)
    thread = threading.Thread(target=proxy.serve_forever, name="compactbench-proxy", daemon=True)
    thread.start()
    return proxy
