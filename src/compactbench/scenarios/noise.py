"""Procedural filler for a software project conversation.

Filler is what makes a case long: source files, test runs, logs, API
responses, git history, metrics tables and the back-and-forth around them.
It is on-topic (same project, same components, same people) so a compactor
can't separate signal from noise by topic alone, but it never states a rule,
a decision or an ownership — those only come from the scenario family, so
every probe stays answerable from the full conversation.

Everything here is generated from templates and seeded randomness: no
model-written text, so the output is free to redistribute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from compactbench.contracts import TurnRole
from compactbench.scenarios.rng import Rng
from compactbench.scenarios.world import Setting


@dataclass(frozen=True)
class TurnDraft:
    role: TurnRole
    content: str
    name: str | None = None
    tags: tuple[str, ...] = field(default=())


def _snake(rng: Rng, setting: Setting) -> str:
    lex = setting.lexicon
    return f"{rng.choice(lex.function_verbs)}_{rng.choice(lex.function_nouns)}"


def _camel(rng: Rng, setting: Setting) -> str:
    lex = setting.lexicon
    noun = rng.choice(lex.function_nouns)
    return f"{rng.choice(lex.function_verbs)}{noun[0].upper()}{noun[1:]}"


def _module(rng: Rng, setting: Setting) -> str:
    component = rng.choice(setting.components)
    return component.replace(" ", "_").replace("-", "_")


def _hexid(rng: Rng, n: int = 7) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def _ts(rng: Rng) -> str:
    return f"2026-0{rng.randint(1, 9)}-{rng.randint(10, 28)}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}Z"


def code_file(rng: Rng, setting: Setting) -> tuple[str, str]:
    """A plausible Python module; returns ``(path, content)``."""
    module = _module(rng, setting)
    path = f"src/{setting.project.lower()}/{module}.py"
    funcs: list[str] = []
    for _ in range(rng.randint(2, 5)):
        name = _snake(rng, setting)
        arg = rng.choice(setting.lexicon.function_nouns)
        limit = rng.choice((10, 25, 50, 100, 250))
        body = rng.choice(
            (
                f"    if not {arg}:\n        return None\n    items = list({arg}.items)[:{limit}]\n"
                f"    return [_normalize(item) for item in items]\n",
                f'    started = time.monotonic()\n    result = client.get(f"/{arg}s/{{{arg}.id}}", timeout=TIMEOUT)\n'
                f'    metrics.observe("{name}.latency", time.monotonic() - started)\n    return result.json()\n',
                f"    for attempt in range(MAX_ATTEMPTS):\n        try:\n            return _send({arg})\n"
                f"        except TransientError:\n            sleep(BACKOFF * (attempt + 1))\n    raise GiveUp({arg}.id)\n",
                f'    key = f"{module}:{{{arg}.id}}"\n    cached = cache.get(key)\n    if cached is not None:\n'
                f"        return cached\n    value = _compute({arg})\n    cache.set(key, value, ttl={limit * 6})\n    return value\n",
            )
        )
        funcs.append(
            f'def {name}({arg}):\n    """{name.replace("_", " ").capitalize()} for the {module.replace("_", " ")}."""\n{body}'
        )
    header = (
        f'"""{module.replace("_", " ").capitalize()} — part of {setting.project}."""\n\n'
        "import time\nfrom time import sleep\n\n"
        f"from {setting.project.lower()}.http import client\nfrom {setting.project.lower()}.observability import metrics\n\n"
        f"TIMEOUT = {rng.choice((2, 3, 5, 8))}\nMAX_ATTEMPTS = {rng.randint(2, 6)}\nBACKOFF = {rng.choice((0.2, 0.5, 1.0))}\n\n\n"
    )
    return path, header + "\n\n".join(funcs)


def test_run(rng: Rng, setting: Setting) -> str:
    module = _module(rng, setting)
    total = rng.randint(24, 140)
    failed = rng.choice((0, 0, 1, 2, 3))
    lines = [f"$ pytest tests/{module} -q"]
    dots = "".join(rng.choice("....F") if failed else "." for _ in range(min(total, 60)))
    lines.append(dots + f" [{rng.randint(40, 100)}%]")
    for _ in range(failed):
        name = _snake(rng, setting)
        lines.append(
            f"FAILED tests/{module}/test_{name}.py::test_{name}_handles_empty - AssertionError: expected {rng.randint(1, 50)}, got {rng.randint(51, 99)}"
        )
    lines.append(f"{total - failed} passed, {failed} failed in {rng.uniform(1.2, 48.0):.2f}s")
    return "\n".join(lines)


def log_tail(rng: Rng, setting: Setting) -> str:
    service = _module(rng, setting)
    lines: list[str] = []
    for _ in range(rng.randint(14, 40)):
        level = rng.choice(("INFO", "INFO", "INFO", "DEBUG", "WARN", "ERROR"))
        endpoint = rng.choice(setting.lexicon.endpoints)
        msg = rng.choice(
            (
                f"handled {rng.choice(('GET', 'POST', 'PATCH'))} {endpoint} status={rng.choice((200, 200, 201, 204, 404, 429, 500))} duration_ms={rng.randint(4, 900)}",
                f"retrying {_snake(rng, setting)} attempt={rng.randint(1, 4)} reason=timeout",
                f"cache miss key={service}:{rng.randint(1000, 99999)}",
                f"queue depth={rng.randint(0, 4000)} lag_ms={rng.randint(0, 9000)}",
                f"connection pool exhausted waiters={rng.randint(1, 30)}",
                f"job {_hexid(rng, 8)} completed rows={rng.randint(10, 90000)}",
            )
        )
        lines.append(f"{_ts(rng)} {level:<5} {service} req={_hexid(rng, 12)} {msg}")
    return "\n".join(lines)


def api_response(rng: Rng, setting: Setting) -> str:
    endpoint = rng.choice(setting.lexicon.endpoints)
    records: list[str] = []
    for _ in range(rng.randint(3, 9)):
        records.append(
            "    {"
            f'"id": "{_hexid(rng, 10)}", "status": "{rng.choice(("active", "pending", "failed", "archived"))}", '
            f'"amount_cents": {rng.randint(100, 900000)}, "created_at": "{_ts(rng)}", '
            f'"attempts": {rng.randint(0, 5)}'
            "}"
        )
    return (
        f'GET {endpoint}?limit={len(records)}\n200 OK\n{{\n  "data": [\n'
        + ",\n".join(records)
        + f'\n  ],\n  "next_cursor": "{_hexid(rng, 16)}"\n}}'
    )


def git_log(rng: Rng, setting: Setting) -> str:
    people = [p for p in setting.cast if p.org is None] or list(setting.cast)
    lines: list[str] = ["$ git log --oneline -n 12"]
    for _ in range(rng.randint(8, 14)):
        author = rng.choice(people)
        msg = rng.choice(
            (
                f"fix: handle empty {rng.choice(setting.lexicon.function_nouns)} in {_snake(rng, setting)}",
                f"refactor: extract {_camel(rng, setting)} helper",
                f"test: cover {_snake(rng, setting)} edge cases",
                "chore: bump lockfile",
                f"perf: batch {rng.choice(setting.lexicon.function_nouns)} writes in {_module(rng, setting)}",
                f"docs: explain {_snake(rng, setting)} retries",
            )
        )
        lines.append(f"{_hexid(rng)} {msg} ({author.first})")
    return "\n".join(lines)


def metrics_table(rng: Rng, setting: Setting) -> str:
    rows = ["| endpoint | p50 ms | p95 ms | error rate |", "|---|---|---|---|"]
    for endpoint in rng.sample(setting.lexicon.endpoints, rng.randint(4, 7)):
        p50 = rng.randint(8, 160)
        rows.append(
            f"| {endpoint} | {p50} | {p50 + rng.randint(20, 700)} | {rng.uniform(0, 2.5):.2f}% |"
        )
    return "\n".join(rows)


def _person(rng: Rng, setting: Setting) -> str:
    return rng.choice(setting.cast).first


def analysis(rng: Rng, setting: Setting) -> str:
    component = rng.choice(setting.components)
    func = _snake(rng, setting)
    sentences = (
        f"The slowdown lines up with the retry loop in `{func}` — each timeout adds a full backoff before the next attempt.",
        f"Most of the failures come from the {component} path; the rest look like flaky fixtures rather than real regressions.",
        f"p95 on {rng.choice(setting.lexicon.endpoints)} went from {rng.randint(120, 300)}ms to {rng.randint(400, 900)}ms, which matches the connection-pool warnings in the logs.",
        f"I'd keep the change small: guard the empty case in `{func}` and add a test for it.",
        f"The cache hit rate is only around {rng.randint(30, 70)}%, so most requests to the {component} still go to the database.",
        "Nothing here points at the deploy itself; the error rate was already creeping up two days earlier.",
        f"There are {rng.randint(2, 9)} call sites for `{func}`; only one of them passes a cursor, so that's where I'd start.",
        f"The importer spends most of its time serializing rows — roughly {rng.randint(55, 85)}% of wall-clock in the last profile.",
        f"If we batch the writes in `{func}`, the job should drop from about {rng.randint(20, 60)} minutes to under {rng.randint(5, 15)}.",
        f"The two failing tests share a fixture that seeds {rng.randint(3, 40)} {rng.choice(setting.lexicon.function_nouns)}s; I suspect ordering, not logic.",
        f"`{_camel(rng, setting)}` swallows the exception and returns an empty list, which is why the caller never retries.",
        f"Memory on the {component} pods climbs about {rng.randint(40, 300)}MB an hour until they're recycled, so there's probably a leak in the buffer pool.",
        f"The queue lag only appears when more than {rng.randint(2, 12)} workers are running, which points at lock contention rather than throughput.",
        f"Half of the 5xx responses are from a single tenant hitting {rng.choice(setting.lexicon.endpoints)} with a malformed cursor.",
        f"The migration script is idempotent, but `{func}` isn't — re-running it would double-count {rng.choice(setting.lexicon.function_nouns)}s.",
        f"Latency is flat until roughly {rng.randint(150, 900)} requests per second, then it falls off a cliff; that's the connection pool size.",
        f"I compared the last {rng.randint(3, 14)} deploys and the regression starts with the one that touched `{_snake(rng, setting)}`.",
        f"The {component} retries on 409s, which it shouldn't — a conflict won't resolve itself on retry.",
        f"Coverage on `{_module(rng, setting)}` is around {rng.randint(35, 92)}%; the untested branch is the one that handles partial pages.",
        f"Most of the log volume is DEBUG lines from `{func}`; dropping them would cut ingest by about {rng.randint(20, 70)}%.",
    )
    picked = rng.sample(sentences, rng.randint(2, 4))
    return " ".join(picked)


def user_request(rng: Rng, setting: Setting) -> str:
    component = rng.choice(setting.components)
    return rng.choice(
        (
            f"Can you pull the recent logs for the {component}?",
            "Run the tests again and tell me what's still failing.",
            f"What does `{_snake(rng, setting)}` actually do?",
            f"Check how the {component} behaves under load.",
            "Show me the latest commits — I want to see what changed since yesterday.",
            f"What do the latency numbers look like for the {component} right now?",
            f"Can you look at the API response for {rng.choice(setting.lexicon.endpoints)}? Something seems off with the cursors.",
            f"Open the {component} module, I want to see how retries work.",
        )
    )


def chatter(rng: Rng, setting: Setting) -> str:
    return rng.choice(
        (
            f"{_person(rng, setting)} is out tomorrow afternoon, so let's not block on them.",
            "Sorry, back — had to jump on another call.",
            f"Quick aside: the demo for {rng.choice(setting.other_projects)} went fine apparently.",
            "Remind me to update the runbook once this is sorted.",
            f"{_person(rng, setting)} asked whether we've looked at the dashboards; I said we're on it.",
            "Let's keep going, I want to get through this before lunch.",
            "Ok. One sec, reading through that.",
        )
    )


def episode(rng: Rng, setting: Setting) -> list[TurnDraft]:
    """One self-contained exchange of filler (user ask → tool use → analysis)."""
    kind = rng.choice(("code", "tests", "logs", "api", "git", "metrics", "talk", "code", "logs"))
    turns: list[TurnDraft] = []
    if kind == "talk":
        turns.append(TurnDraft(TurnRole.USER, chatter(rng, setting)))
        turns.append(TurnDraft(TurnRole.ASSISTANT, analysis(rng, setting)))
        return turns

    turns.append(TurnDraft(TurnRole.USER, user_request(rng, setting)))
    if kind == "code":
        path, content = code_file(rng, setting)
        turns.append(TurnDraft(TurnRole.ASSISTANT, f"Opening `{path}`."))
        turns.append(TurnDraft(TurnRole.TOOL, content, name="read_file"))
    elif kind == "tests":
        turns.append(TurnDraft(TurnRole.ASSISTANT, "Running the test suite."))
        turns.append(TurnDraft(TurnRole.TOOL, test_run(rng, setting), name="run_tests"))
    elif kind == "logs":
        turns.append(TurnDraft(TurnRole.ASSISTANT, "Pulling the last few minutes of logs."))
        turns.append(TurnDraft(TurnRole.TOOL, log_tail(rng, setting), name="tail_logs"))
    elif kind == "api":
        turns.append(TurnDraft(TurnRole.ASSISTANT, "Calling the endpoint."))
        turns.append(TurnDraft(TurnRole.TOOL, api_response(rng, setting), name="http_get"))
    elif kind == "git":
        turns.append(TurnDraft(TurnRole.ASSISTANT, "Checking the history."))
        turns.append(TurnDraft(TurnRole.TOOL, git_log(rng, setting), name="shell"))
    else:
        turns.append(TurnDraft(TurnRole.ASSISTANT, "Querying the metrics."))
        turns.append(TurnDraft(TurnRole.TOOL, metrics_table(rng, setting), name="query_metrics"))
    turns.append(TurnDraft(TurnRole.ASSISTANT, analysis(rng, setting)))
    return turns


def _note_bullets(rng: Rng, setting: Setting, count: int) -> list[str]:
    bullets = (
        f"{_person(rng, setting)} finished the load test on the {rng.choice(setting.components)}; p95 held at {rng.randint(90, 400)}ms.",
        f"Flaky test in `{_snake(rng, setting)}` still open, {_person(rng, setting)} to look at fixtures.",
        f"Dashboards for the {rng.choice(setting.components)} are up but need better alert thresholds.",
        f"Customer report about duplicate {rng.choice(setting.lexicon.function_nouns)}s — couldn't reproduce yet.",
        f"Docs for the {rng.choice(setting.components)} are out of date; nobody has picked that up.",
        f"Staging was down for ~{rng.randint(10, 50)} minutes on Tuesday (expired cert).",
        f"Error budget for the month is about {rng.randint(20, 90)}% used.",
        f"{_person(rng, setting)} raised that the runbook for {rng.choice(setting.other_projects)} is a good template.",
        f"Next sync moved to {rng.choice(('Monday', 'Tuesday', 'Wednesday', 'Thursday'))}.",
        f"Backlog grooming: {rng.randint(8, 30)} tickets closed as stale.",
    )
    return rng.sample(bullets, min(count, len(bullets)))


def embed(rng: Rng, setting: Setting, sentence: str) -> list[TurnDraft]:
    """Bury ``sentence`` in the middle of a long pasted document or tool output."""
    style = rng.choice(("notes", "ticket", "doc"))
    if style == "notes":
        bullets = _note_bullets(rng, setting, rng.randint(6, 9))
        bullets.insert(rng.randint(2, len(bullets) - 2), sentence)
        content = f"Pasting the notes from this morning's {setting.project} sync:\n" + "\n".join(
            f"- {b}" for b in bullets
        )
        return [
            TurnDraft(TurnRole.USER, content, tags=("embedded",)),
            TurnDraft(
                TurnRole.ASSISTANT,
                "Thanks — mostly status updates. Anything you want me to pick up first?",
            ),
        ]
    if style == "ticket":
        ticket = f"{rng.choice(setting.lexicon.ticket_prefixes)}-{rng.randint(1000, 9999)}"
        bullets = _note_bullets(rng, setting, rng.randint(4, 6))
        bullets.insert(rng.randint(1, len(bullets) - 1), sentence)
        body = "\n".join(f"* {b}" for b in bullets)
        content = (
            f"{ticket}: {setting.project} — {rng.choice(setting.components)} follow-ups\n"
            f"Status: In progress\nReporter: {rng.choice(setting.cast).name}\n\nDescription:\n{body}"
        )
        return [
            TurnDraft(TurnRole.USER, f"Can you pull up {ticket}?"),
            TurnDraft(TurnRole.TOOL, content, name="get_ticket", tags=("embedded",)),
            TurnDraft(TurnRole.ASSISTANT, "Got it. It's mostly follow-ups from the last sprint."),
        ]
    path, code = code_file(rng, setting)
    lines = code.splitlines()
    doc_lines = [
        f"# {setting.project} engineering notes",
        "",
        "## Context",
        analysis(rng, setting),
        "",
        "## Working agreements",
        sentence,
        "",
        "## Implementation sketch",
        "```python",
        *lines[: rng.randint(10, max(11, len(lines)))],
        "```",
    ]
    doc_path = path.replace("src/", "docs/").replace(".py", ".md")
    return [
        TurnDraft(TurnRole.USER, f"Read `{doc_path}` before we go further."),
        TurnDraft(TurnRole.TOOL, "\n".join(doc_lines), name="read_file", tags=("embedded",)),
        TurnDraft(
            TurnRole.ASSISTANT,
            "Read it. The implementation sketch is close to what's in the repo now.",
        ),
    ]


class NoiseSource(Protocol):
    """Where filler comes from. Ranked suite packs supply their own."""

    def episode(self, rng: Rng, setting: Setting) -> list[TurnDraft]:
        """One self-contained filler exchange."""
        ...

    def embed(self, rng: Rng, setting: Setting, sentence: str) -> list[TurnDraft]:
        """Turns that bury ``sentence`` inside a longer document or tool output."""
        ...


@dataclass(frozen=True)
class _PublicNoise:
    def episode(self, rng: Rng, setting: Setting) -> list[TurnDraft]:
        return episode(rng, setting)

    def embed(self, rng: Rng, setting: Setting, sentence: str) -> list[TurnDraft]:
        return embed(rng, setting, sentence)


PUBLIC_NOISE: NoiseSource = _PublicNoise()
