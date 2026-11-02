"""CompactBench command-line interface."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.table import Table

from compactbench import __version__
from compactbench.config import load_dotenv

app = typer.Typer(
    name="compactbench",
    help="The benchmark for LLM context compaction.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"compactbench {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    _version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """CompactBench CLI."""
    # Runs before any subcommand, so providers constructed downstream see the
    # variables. `.env` is documented as the way to supply API keys.
    load_dotenv()


def _difficulty(value: str | None) -> Any:
    from compactbench.scenarios import Difficulty

    if value is None:
        return None
    try:
        return Difficulty(value.lower())
    except ValueError as exc:
        console.print(
            f"[red]unknown difficulty {value!r}. Valid: {[d.value for d in Difficulty]}[/red]"
        )
        raise typer.Exit(code=1) from exc


def _effort(value: str | None) -> Any:
    if value is None:
        return None
    if value not in ("low", "medium", "high"):
        console.print(f"[red]unknown reader effort {value!r}. Valid: low, medium, high[/red]")
        raise typer.Exit(code=1)
    return value


def _load_pack(path: Path | None) -> None:
    from compactbench.scenarios import load_suite_pack

    if path is None:
        return
    try:
        suites = load_suite_pack(path)
    except ImportError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"loaded suite pack {path}: {', '.join(s.key for s in suites)}")


@app.command()
def run(
    method: str = typer.Option(
        ..., "--method", "-m", help="'built-in:<key>' or '<path.py>:<ClassName>'."
    ),
    suite: str = typer.Option("starter", "--suite", "-s", help="Suite key (see `suites list`)."),
    provider: str = typer.Option(
        "mock", "--provider", "-p", help="Provider the method uses for its own calls."
    ),
    model: str = typer.Option("mock-deterministic", "--model", help="Model the method uses."),
    reader_provider: str | None = typer.Option(
        None, "--reader-provider", help="Provider for the reader (default: --provider)."
    ),
    reader_model: str | None = typer.Option(
        None, "--reader-model", help="Model that answers the probes (default: --model)."
    ),
    reader_effort: str | None = typer.Option(
        None,
        "--reader-effort",
        help="Reasoning effort for the reader (low|medium|high), where the provider supports it.",
    ),
    budget: int = typer.Option(
        2048,
        "--budget",
        min=0,
        help="Token budget for each artifact (cl100k_base). 0 disables the budget.",
    ),
    difficulty: str | None = typer.Option(
        None, "--difficulty", help="Override the suite's difficulty: easy|medium|hard|elite."
    ),
    drift_cycles: int | None = typer.Option(
        None, "--drift-cycles", min=0, max=8, help="Override the number of drift cycles."
    ),
    cases: int | None = typer.Option(
        None, "--cases", min=1, help="Cases per family (default: the suite's)."
    ),
    seed_group: str = typer.Option("default", "--seed-group"),
    controls: bool = typer.Option(
        False,
        "--controls/--no-controls",
        help="Also answer every probe from the full conversation and from nothing, "
        "so the run carries its own ceiling and floor.",
    ),
    output: Path = typer.Option(Path("results.jsonl"), "--output", "-o"),
    traces: Path | None = typer.Option(
        None,
        "--traces",
        help="Write full per-cycle traces (conversation, artifacts, answers) here. "
        "Keep private for hidden suites.",
    ),
    resume: bool = typer.Option(False, "--resume", help="Skip cases already in --output."),
    concurrency: int = typer.Option(4, "--concurrency", min=1, max=32),
    season: Path | None = typer.Option(
        None, "--season", help="Season file; pins every setting except method and its model."
    ),
    suite_pack: Path | None = typer.Option(
        None, "--suite-pack", help="Private suite pack (a .py file) to load first."
    ),
    estimate: bool = typer.Option(
        False, "--estimate", help="Print projected calls, tokens and cost; make no API calls."
    ),
    method_config: str = typer.Option(
        "{}", "--method-config", help="JSON object passed to the method as self.config."
    ),
    sandbox_image: str | None = typer.Option(
        None,
        "--sandbox-image",
        help="Run the method inside this container image instead of importing it "
        "(ranked evaluation). --method is resolved inside the container.",
    ),
    sandbox_network: str = typer.Option(
        "none", "--sandbox-network", help="Docker network the sandbox joins (the model proxy's)."
    ),
    sandbox_runtime: str | None = typer.Option(
        None, "--sandbox-runtime", help="Container runtime for the sandbox, e.g. runsc (gVisor)."
    ),
    sandbox_endpoint_kind: str = typer.Option(
        "default",
        "--sandbox-endpoint-kind",
        help="'custom' when the method's calls go to the submitter's own endpoint.",
    ),
    sandbox_env: list[str] = typer.Option(
        [],
        "--sandbox-env",
        help="KEY=VALUE set in the sandbox, e.g. ANTHROPIC_BASE_URL=http://proxy:8080/anthropic.",
    ),
    declared_name: str | None = typer.Option(
        None, "--method-name", hidden=True, help="Sandbox mode: record the run under this name."
    ),
    declared_version: str | None = typer.Option(
        None, "--method-version", hidden=True, help="Sandbox mode: and this version."
    ),
) -> None:
    """Run a compaction method against a suite."""
    import asyncio

    from compactbench.runner import RunArgs, RunnerError, run_experiment

    _load_pack(suite_pack)
    season_key: str | None = None
    budget_tokens: int | None = budget or None
    level = _difficulty(difficulty)
    if season is not None:
        from compactbench.leaderboard import load_season

        pinned = load_season(season)
        if pinned.suite_pack:
            _load_pack(season.parent / pinned.suite_pack)
        season_key = pinned.key
        suite, level = pinned.suite, pinned.difficulty
        drift_cycles, cases = pinned.drift_cycles, pinned.cases_per_family
        budget_tokens, controls = pinned.budget_tokens, pinned.controls
        reader_provider, reader_model = pinned.reader.provider, pinned.reader.model
        reader_effort = pinned.reader.effort
        if pinned.sampling == "fresh":
            # Resuming continues the sample the run started with; a new run draws its own.
            from compactbench.runner.persistence import read_run_start

            existing = read_run_start(output) if resume and output.exists() else None
            seed_group = (
                existing.seed_group
                if existing is not None
                else f"{pinned.seed_group}/{secrets.token_hex(8)}"
            )
        else:
            seed_group = pinned.seed_group
        console.print(
            f"season {pinned.key}: suite={suite} difficulty={level.value} drift_cycles={drift_cycles} "
            f"cases={cases} budget={budget_tokens} reader={reader_provider}/{reader_model} "
            f"controls={controls}"
        )

    import json

    parsed_config = json.loads(method_config)
    if not isinstance(parsed_config, dict):
        raise typer.BadParameter("--method-config must be a JSON object")

    sandbox = None
    if sandbox_image is not None:
        from compactbench.sandbox import Sandbox

        pairs: list[tuple[str, str]] = []
        for item in sandbox_env:
            key, sep, value = item.partition("=")
            if not sep or not key:
                raise typer.BadParameter(f"--sandbox-env expects KEY=VALUE, got {item!r}")
            pairs.append((key, value))
        sandbox = Sandbox.docker(
            sandbox_image, network=sandbox_network, env=pairs, runtime=sandbox_runtime
        )
    if (declared_name is None) != (declared_version is None):
        raise typer.BadParameter("--method-name and --method-version go together")
    if declared_name is not None and sandbox is None:
        raise typer.BadParameter("--method-name only applies with --sandbox-image")
    declared = (declared_name, declared_version) if declared_name and declared_version else None

    args = RunArgs(
        method_spec=method,
        suite=suite,
        provider_key=provider,
        model=model,
        output_path=output,
        reader_provider_key=reader_provider,
        reader_model=reader_model,
        reader_effort=_effort(reader_effort),
        difficulty=level,
        drift_cycles=drift_cycles,
        cases_per_family=cases,
        seed_group=seed_group,
        budget_tokens=budget_tokens,
        controls=controls,
        traces_path=traces,
        resume=resume,
        concurrency=concurrency,
        season=season_key,
        sandbox=sandbox,
        sandbox_endpoint_kind=sandbox_endpoint_kind,
        declared_method=declared,
        method_config=cast("dict[str, Any]", parsed_config),
    )

    if estimate:
        _print_estimate(args)
        return

    try:
        asyncio.run(run_experiment(args))
    except RunnerError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]wrote {output}[/green]")
    console.print(f"run 'compactbench score --results {output}' for a summary.")


def _print_estimate(args: Any) -> None:
    from compactbench.runner.estimate import estimate_run, format_estimate
    from compactbench.scenarios import expand_suite, get_suite

    try:
        suite = get_suite(args.suite)
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    cases = expand_suite(
        suite,
        seed_group=args.seed_group,
        cases_per_family=args.cases_per_family,
        difficulty=args.difficulty,
        drift_cycles=args.drift_cycles,
    )
    report = estimate_run(
        cases,
        provider_key=args.provider_key,
        model=args.model,
        reader_provider_key=args.resolved_reader_provider,
        reader_model=args.resolved_reader_model,
        budget_tokens=args.budget_tokens,
        controls=args.controls,
    )
    console.print(format_estimate(report), highlight=False)


@app.command()
def generate(
    family: str = typer.Option(..., "--family", "-f", help="Family key (see `families list`)."),
    seed: int = typer.Option(0, "--seed"),
    difficulty: str = typer.Option("medium", "--difficulty"),
    drift_cycles: int | None = typer.Option(None, "--drift-cycles", min=0, max=8),
    text: bool = typer.Option(
        False, "--text", help="Print a readable transcript and probes instead of JSON."
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write to this file."),
    suite_pack: Path | None = typer.Option(None, "--suite-pack"),
) -> None:
    """Generate one case from a family and seed."""
    from compactbench.rendering import render_turns
    from compactbench.scenarios import UnknownFamilyError, generate_case

    _load_pack(suite_pack)
    try:
        case = generate_case(family, seed, _difficulty(difficulty), drift_cycles=drift_cycles)
    except UnknownFamilyError as exc:
        console.print(f"[red]{exc.args[0]}[/red]")
        raise typer.Exit(code=1) from exc

    if text:
        blocks: list[str] = []
        for spec in case.cycles:
            blocks.append(f"===== cycle {spec.cycle} ({len(spec.turns)} turns) =====")
            blocks.append(render_turns(spec.turns))
            blocks.append(f"----- probes after compaction {spec.cycle} -----")
            for p in spec.probes:
                options = "".join(f"\n    - {o}" for o in p.options)
                blocks.append(
                    f"[{p.category.value}/{p.format.value}] {p.question}{options}\n"
                    f"    answer: {p.answer}  stale: {p.stale}"
                )
        rendered = "\n\n".join(blocks)
    else:
        rendered = case.model_dump_json(indent=2)

    if output is None:
        if text:
            console.print(rendered, highlight=False, markup=False)
        else:
            console.print_json(rendered)
    else:
        output.write_text(rendered + "\n", encoding="utf-8")
        console.print(f"wrote {output}")


@app.command()
def score(
    results: Path = typer.Option(..., "--results", "-r", exists=True, readable=True),
) -> None:
    """Summarize a ``results.jsonl`` file produced by ``compactbench run``."""
    from compactbench.runner import to_run_result

    try:
        run_result = to_run_result(results)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    m = run_result.metrics

    header = Table(title="Run")
    header.add_column("Field")
    header.add_column("Value")
    header.add_row("method", f"{run_result.method_name} ({run_result.method_version})")
    header.add_row(
        "method model", f"{run_result.compactor_provider} / {run_result.compactor_model}"
    )
    header.add_row("reader", f"{run_result.reader_provider} / {run_result.reader_model}")
    header.add_row(
        "suite", f"{run_result.suite}@{run_result.suite_version} ({run_result.difficulty})"
    )
    header.add_row("drift cycles", str(run_result.drift_cycles))
    header.add_row("budget", str(run_result.budget_tokens or "none"))
    header.add_row("season", run_result.season or "—")
    header.add_row("scorer", run_result.scorer_version)
    header.add_row("cases", str(len(run_result.cases)))
    console.print(header)

    families = Table(title="By family")
    families.add_column("Family")
    families.add_column("Score", justify="right")
    families.add_column("Oracle", justify="right")
    families.add_column("Null", justify="right")
    families.add_column("Normalized", justify="right")
    families.add_column("Probes", justify="right")
    for family, fm in m.by_family.items():
        families.add_row(
            family,
            f"{fm.score:.3f}",
            _fmt_opt(fm.oracle_score),
            _fmt_opt(fm.null_score),
            _fmt_opt(fm.normalized_score),
            str(fm.probes),
        )
    console.print(families)

    categories = Table(title="By probe category")
    categories.add_column("Category")
    categories.add_column("Score", justify="right")
    categories.add_column("Probes", justify="right")
    for category, cm in sorted(m.by_category.items(), key=lambda kv: kv[1].score):
        categories.add_row(category, f"{cm.score:.3f}", str(cm.probes))
    console.print(categories)

    summary = Table(title="Aggregate")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("score", f"{m.score:.3f}  (95% CI {m.score_ci_low:.3f}-{m.score_ci_high:.3f})")
    summary.add_row("normalized score", _fmt_opt(m.normalized_score))
    summary.add_row("score by cycle", "  ".join(f"{s:.2f}" for s in m.by_cycle))
    summary.add_row("drift resistance", f"{m.drift_resistance:.3f}")
    summary.add_row("decay (first - last)", f"{m.decay:+.3f}")
    summary.add_row("stale-answer rate", f"{m.stale_rate:.1%}")
    summary.add_row("trap rate", f"{m.trap_rate:.1%}")
    summary.add_row("hallucination rate", f"{m.hallucination_rate:.1%}")
    summary.add_row("mean artifact tokens", f"{m.mean_artifact_tokens:,.0f}")
    summary.add_row("compression ratio", f"{m.compression_ratio:.1f}x")
    summary.add_row("budget violations", str(m.budget_violations))
    summary.add_row("reader error rate", f"{m.reader_error_rate:.1%}")
    console.print(summary)

    usage = run_result.token_usage
    if usage is not None and usage.call_count:
        tokens = Table(title="Token usage (method + reader + controls)")
        tokens.add_column("Metric")
        tokens.add_column("Value", justify="right")
        tokens.add_row("api_calls", f"{usage.call_count:,}")
        tokens.add_row("prompt_tokens", f"{usage.prompt_tokens:,}")
        tokens.add_row("completion_tokens", f"{usage.completion_tokens:,}")
        if usage.cached_prompt_tokens:
            tokens.add_row("cached_prompt_tokens", f"{usage.cached_prompt_tokens:,}")
        console.print(tokens)

    warned = sum(1 for case in run_result.cases for c in case.cycles if c.warnings)
    if warned:
        console.print(
            f"[yellow]{warned} cycle(s) carry method warnings — see `warnings` in "
            f"{results}[/yellow]"
        )
    for note in run_result.notes:
        console.print(f"[yellow]note: {note}[/yellow]")


def _fmt_opt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


@app.command()
def qualify(
    results: Path = typer.Option(..., "--results", "-r", exists=True, readable=True),
    season: Path | None = typer.Option(
        None, "--season", help="Also check the run against this season's pinned settings."
    ),
) -> None:
    """Check whether a results file would qualify for the leaderboard, and why not.

    Runs the same floors the submission pipeline applies, locally — so a
    disqualification shows up before anyone opens a PR or spends more budget.
    """
    from compactbench.leaderboard import load_season
    from compactbench.leaderboard import qualify as qualify_run
    from compactbench.runner import to_run_result

    try:
        run_result = to_run_result(results)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    outcome = qualify_run(run_result, season=load_season(season) if season else None)
    m = run_result.metrics
    console.print(
        f"{run_result.method_name}: score {m.score:.3f} "
        f"(95% CI {m.score_ci_low:.3f}-{m.score_ci_high:.3f}), "
        f"drift resistance {m.drift_resistance:.3f}"
    )
    if outcome.qualified:
        console.print("[green]QUALIFIED[/green] — this run meets every leaderboard floor.")
        return
    console.print("[red]NOT QUALIFIED[/red]")
    for reason in outcome.reasons:
        console.print(f"  • {reason}")
    raise typer.Exit(code=1)


@app.command()
def submit(
    results: Path = typer.Option(..., "--results", "-r", exists=True, readable=True),
    method_name: str = typer.Option(..., "--name", help="Method name in kebab-case."),
) -> None:
    """Print the steps to submit a method for ranked scoring."""
    console.print("[bold]Submit a method to the CompactBench leaderboard[/bold]\n")
    console.print(f"  1. Check it qualifies: compactbench qualify --results {results}")
    console.print(
        f"  2. Ranked submissions for [cyan]{method_name}[/cyan] are paused while the v2 "
        "evaluation pipeline is finished."
    )
    console.print("     Until then, develop against the public practice suite.")
    console.print(
        "\nDetails: https://github.com/compactbench/compactbench/blob/main/docs/submitting.md"
    )


@app.command("sandbox-serve", hidden=True)
def sandbox_serve(
    method: str = typer.Option(..., "--method"),
    provider: str = typer.Option(..., "--provider"),
    model: str = typer.Option(..., "--model"),
    config: str = typer.Option("{}", "--config", help="Method config as JSON."),
) -> None:
    """Serve compaction requests over stdin/stdout (runs inside the ranked sandbox)."""
    import json

    from compactbench.sandbox import serve

    parsed = json.loads(config)
    if not isinstance(parsed, dict):
        raise typer.BadParameter("--config must be a JSON object")
    serve(method, provider, model, cast("dict[str, Any]", parsed))


keys_app = typer.Typer(help="Seal provider keys for ranked evaluation.", no_args_is_help=True)
app.add_typer(keys_app, name="keys")


@keys_app.command("seal")
def keys_seal(
    season: Path = typer.Option(..., "--season", exists=True, readable=True),
    submission: str = typer.Option(
        ..., "--submission", help="<handle>/<method>, exactly as your submission directory."
    ),
) -> None:
    """Seal your provider API key so only the ranked evaluation proxy can read it."""
    import getpass
    import sys

    from compactbench.leaderboard import load_season
    from compactbench.sealing import key_context, seal

    pinned = load_season(season)
    if not pinned.public_key:
        console.print(f"[red]{season} has no public_key; ranked evaluation isn't open.[/red]")
        raise typer.Exit(code=1)
    secret = (
        sys.stdin.readline().strip()
        if not sys.stdin.isatty()
        else getpass.getpass("Provider API key (input hidden): ").strip()
    )
    if not secret:
        console.print("[red]no key given[/red]")
        raise typer.Exit(code=1)
    sealed = seal(
        pinned.public_key, secret.encode("utf-8"), context=key_context(pinned.key, submission)
    )
    # Plain print: the value goes straight into config.yaml.
    print(sealed)


@keys_app.command("seal-file", hidden=True)
def keys_seal_file(
    source: Path = typer.Argument(..., exists=True, readable=True),
    target: Path = typer.Argument(...),
    public_key: str = typer.Option(..., "--public-key", help="Recipient public key."),
    context: str = typer.Option(..., "--context", help="What the file is, e.g. traces:<run id>."),
) -> None:
    """Seal a file (ranked traces) and print the SHA-256 of its plaintext as a commitment."""
    import hashlib

    from compactbench.sealing import seal

    data = source.read_bytes()
    target.write_text(seal(public_key, data, context=context), encoding="ascii")
    print(f"sha256:{hashlib.sha256(data).hexdigest()}")


@keys_app.command("generate", hidden=True)
def keys_generate(
    private_out: Path = typer.Option(
        ..., "--private-out", help="New file for the private key (created with mode 600)."
    ),
) -> None:
    """Make a keypair (maintainers). Prints the public key; the private key goes to a file."""
    import os

    from compactbench.sealing import generate_keypair

    private, public = generate_keypair()
    try:
        fd = os.open(private_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        console.print(f"[red]{private_out} already exists; not overwriting it.[/red]")
        raise typer.Exit(code=1) from None
    with os.fdopen(fd, "w") as handle:
        handle.write(private + "\n")
    print(public)


@app.command("proxy", hidden=True)
def proxy_command(
    listen: str = typer.Option("0.0.0.0:8080", "--listen", help="host:port"),
    route: str = typer.Option(..., "--route", help="Provider route the key is for."),
    allow_model: list[str] = typer.Option([], "--allow-model", help="Model the run may call."),
    sealed_key: Path | None = typer.Option(
        None, "--sealed-key", help="File holding the submitter's sealed key."
    ),
    context: str | None = typer.Option(None, "--context", help="Context the key was sealed under."),
    max_requests: int = typer.Option(10_000, "--max-requests", min=1),
    max_tokens: int = typer.Option(50_000_000, "--max-tokens", min=1),
    log: Path | None = typer.Option(None, "--log", help="Call log (no bodies)."),
    upstream: str | None = typer.Option(
        None, "--upstream", help="Base URL of the submitter's endpoint (route 'custom')."
    ),
    no_key: bool = typer.Option(
        False, "--no-key", help="Forward without a key (a custom endpoint that takes none)."
    ),
) -> None:
    """Run the ranked evaluation's model proxy in the foreground (maintainers / CI).

    The key comes from ``--sealed-key`` (opened with COMPACTBENCH_SEASON_PRIVATE_KEY)
    or, for local testing, from COMPACTBENCH_PROXY_KEY.
    """
    import os
    import signal
    import threading

    from compactbench.proxy import ROUTES, ModelProxy, ProxyConfig, custom_upstream
    from compactbench.sealing import open_sealed

    routes = dict(ROUTES)
    if route == "custom":
        if not upstream:
            raise typer.BadParameter("route 'custom' needs --upstream")
        routes["custom"] = custom_upstream(upstream)
    elif route not in ROUTES:
        raise typer.BadParameter(f"unknown route {route!r}; known: {sorted(ROUTES)} or custom")
    if sealed_key is not None:
        private = os.environ.pop("COMPACTBENCH_SEASON_PRIVATE_KEY", "")
        if not private or context is None:
            raise typer.BadParameter(
                "--sealed-key needs --context and COMPACTBENCH_SEASON_PRIVATE_KEY"
            )
        secret = open_sealed(private, sealed_key.read_text(encoding="utf-8"), context=context)
        key = secret.decode("utf-8")
    elif no_key:
        if route != "custom":
            raise typer.BadParameter("--no-key is only for route 'custom'")
        key = ""
    else:
        key = os.environ.pop("COMPACTBENCH_PROXY_KEY", "")
        if not key:
            raise typer.BadParameter("set COMPACTBENCH_PROXY_KEY, pass --sealed-key or --no-key")
    host, _, port = listen.rpartition(":")
    config = ProxyConfig(
        keys={route: key},
        models=frozenset(allow_model),
        max_requests=max_requests,
        max_tokens=max_tokens,
        log_path=log,
        routes=routes,
    )
    server = ModelProxy((host or "0.0.0.0", int(port)), config)

    def _stop(signum: int, frame: object) -> None:
        # shutdown() waits for serve_forever(), which runs on this thread.
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _stop)
    console.print(f"proxy listening on {listen} for {route}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        stats = server.stats
        console.print(
            f"proxy stopped: {stats.requests} requests, {stats.input_tokens} in, "
            f"{stats.output_tokens} out, {stats.refused} refused"
        )


providers_app = typer.Typer(help="Inspect available model providers.", no_args_is_help=True)
suites_app = typer.Typer(help="Inspect available suites.", no_args_is_help=True)
families_app = typer.Typer(help="Inspect scenario families.", no_args_is_help=True)
app.add_typer(providers_app, name="providers")
app.add_typer(suites_app, name="suites")
app.add_typer(families_app, name="families")


@providers_app.command("list")
def providers_list() -> None:
    """List registered model providers."""
    from compactbench.providers import list_providers

    notes: dict[str, str] = {
        "mock": "offline, canned responses — for tests",
        "anthropic": "Claude. Set COMPACTBENCH_ANTHROPIC_API_KEY.",
        "openai": "OpenAI or any OpenAI-compatible server. Set COMPACTBENCH_OPENAI_API_KEY "
        "(and COMPACTBENCH_OPENAI_BASE_URL for compatible servers).",
        "groq": "Groq Cloud. Set COMPACTBENCH_GROQ_API_KEY.",
        "google-ai-studio": "Google AI Studio. Set COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY.",
        "ollama": "Local Ollama. COMPACTBENCH_OLLAMA_BASE_URL (default localhost:11434).",
    }
    table = Table(title="Model providers")
    table.add_column("Key")
    table.add_column("Notes")
    for key in list_providers():
        table.add_row(key, notes.get(key, ""))
    console.print(table)


@suites_app.command("list")
def suites_list(
    suite_pack: Path | None = typer.Option(None, "--suite-pack"),
) -> None:
    """List available suites."""
    from compactbench.scenarios import PROFILES, SUITES

    _load_pack(suite_pack)
    table = Table(title="Suites")
    table.add_column("Suite")
    table.add_column("Version")
    table.add_column("Difficulty")
    table.add_column("Cases/family", justify="right")
    table.add_column("Opening tokens", justify="right")
    table.add_column("Families")
    for suite in SUITES.values():
        profile = PROFILES[suite.difficulty]
        table.add_row(
            suite.key,
            suite.version,
            suite.difficulty.value,
            str(suite.cases_per_family),
            f"~{profile.initial_tokens:,}",
            ", ".join(suite.families),
        )
    console.print(table)


@families_app.command("list")
def families_list() -> None:
    """List scenario families."""
    from compactbench.scenarios import get_family, list_families

    table = Table(title="Families")
    table.add_column("Key")
    table.add_column("Version")
    table.add_column("What it tests")
    for key in list_families():
        family = get_family(key)
        table.add_row(key, family.version, family.description)
    console.print(table)
