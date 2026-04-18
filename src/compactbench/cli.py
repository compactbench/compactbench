"""CompactBench command-line interface.

Implemented incrementally. Each command raises ``NotImplementedError`` until its
backing workorder lands. See docs/architecture/workorders.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from compactbench import __version__
from compactbench.config import default_benchmarks_dir

app = typer.Typer(
    name="compactbench",
    help="Open benchmark for AI conversation compaction methods.",
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


@app.command()
def run(
    method: str = typer.Option(
        ..., "--method", "-m", help="Method id: 'built-in:<key>' or '<path.py>:<ClassName>'."
    ),
    suite: str = typer.Option("starter", "--suite", "-s", help="Benchmark suite key."),
    provider: str = typer.Option("mock", "--provider", "-p", help="Model provider key."),
    model: str = typer.Option("mock-deterministic", "--model", help="Provider-specific model key."),
    difficulty: str = typer.Option("medium", "--difficulty"),
    drift_cycles: int = typer.Option(2, "--drift-cycles", min=0, max=5),
    case_count: int = typer.Option(
        5,
        "--case-count",
        min=1,
        help=(
            "Cases per template. 5 is enough for per-family std-dev to be "
            "meaningful; 20+ is standard for ranked submissions. Lower values "
            "run faster but give noisy scores."
        ),
    ),
    seed_group: str = typer.Option("default", "--seed-group"),
    benchmarks_dir: Path = typer.Option(
        default_benchmarks_dir(),
        "--benchmarks-dir",
        help="Directory containing benchmark suites.",
    ),
    output: Path = typer.Option(Path("results.jsonl"), "--output", "-o"),
    resume: bool = typer.Option(
        False, "--resume", help="Continue from existing output file (skip completed cases)."
    ),
    concurrency: int = typer.Option(
        4,
        "--concurrency",
        min=1,
        max=32,
        help=(
            "Maximum concurrent cases. Set to 1 for strict serial execution. "
            "Higher values give near-linear wall-clock speedup until the provider's "
            "rate limit dominates; 4 is a safe default on most free tiers."
        ),
    ),
    estimate: bool = typer.Option(
        False,
        "--estimate",
        help=(
            "Print projected API calls, tokens, and dollar cost without making any "
            "provider calls. Use this to size a run before committing real quota."
        ),
    ),
) -> None:
    """Run a compaction method against a benchmark suite."""
    import asyncio

    from compactbench.dsl import DifficultyLevel
    from compactbench.runner import RunArgs, RunnerError, run_experiment

    try:
        diff = DifficultyLevel(difficulty.lower())
    except ValueError as exc:
        console.print(
            f"[red]unknown difficulty {difficulty!r}. "
            f"Valid: {[d.value for d in DifficultyLevel]}[/red]"
        )
        raise typer.Exit(code=1) from exc

    args = RunArgs(
        method_spec=method,
        suite_key=suite,
        provider_key=provider,
        model=model,
        difficulty=diff,
        drift_cycles=drift_cycles,
        case_count_per_template=case_count,
        seed_group=seed_group,
        benchmarks_dir=benchmarks_dir,
        output_path=output,
        resume=resume,
        concurrency=concurrency,
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
    """Load the suite, project cost + tokens, and print the report. No API calls."""
    from compactbench.dsl import TemplateError, load_suite, validate_template
    from compactbench.runner.estimate import estimate_run, format_estimate

    suite_dir = args.benchmarks_dir / args.suite_key
    if not suite_dir.is_dir():
        console.print(f"[red]suite directory not found: {suite_dir}[/red]")
        raise typer.Exit(code=1)

    try:
        templates = load_suite(suite_dir)
        for t in templates:
            validate_template(t)
    except TemplateError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not templates:
        console.print(f"[red]no templates in suite {args.suite_key!r}[/red]")
        raise typer.Exit(code=1)

    versions = {t.version for t in templates}
    suite_version = next(iter(versions)) if len(versions) == 1 else "mixed"

    report = estimate_run(
        templates=templates,
        suite_key=args.suite_key,
        suite_version=suite_version,
        seed_group=args.seed_group,
        case_count_per_template=args.case_count_per_template,
        difficulty=args.difficulty,
        drift_cycles=args.drift_cycles,
        provider_key=args.provider_key,
        model=args.model,
    )
    console.print(format_estimate(report))


@app.command()
def generate(
    template: str = typer.Option(..., "--template", "-t", help="Template key."),
    seed: int = typer.Option(0, "--seed"),
    difficulty: str = typer.Option("medium", "--difficulty"),
    benchmarks_dir: Path = typer.Option(
        default_benchmarks_dir(),
        "--benchmarks-dir",
        help="Directory containing public benchmark suites.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write JSON to this file (stdout if omitted)."
    ),
) -> None:
    """Generate a single benchmark case from a template and seed."""
    from compactbench.dsl import (
        DifficultyLevel,
        TemplateError,
        load_suite,
        validate_template,
    )
    from compactbench.engine import generate_case

    if not benchmarks_dir.is_dir():
        console.print(f"[red]no benchmarks directory at {benchmarks_dir}[/red]")
        raise typer.Exit(code=1)

    found: dict[str, Any] = {}
    for suite_dir in sorted(p for p in benchmarks_dir.iterdir() if p.is_dir()):
        try:
            for t in load_suite(suite_dir):
                found[t.key] = t
        except TemplateError as exc:
            console.print(f"[yellow]skipping {suite_dir.name}: {exc}[/yellow]")

    if template not in found:
        console.print(f"[red]template {template!r} not found. Known: {sorted(found)}[/red]")
        raise typer.Exit(code=1)

    tmpl = found[template]
    try:
        validate_template(tmpl)
    except TemplateError as exc:
        console.print(f"[red]template {template!r} failed validation: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        diff = DifficultyLevel(difficulty.lower())
    except ValueError as exc:
        console.print(
            f"[red]unknown difficulty {difficulty!r}. "
            f"Valid: {[d.value for d in DifficultyLevel]}[/red]"
        )
        raise typer.Exit(code=1) from exc

    case = generate_case(tmpl, seed, diff)
    json_text = case.model_dump_json(indent=2)
    if output is None:
        console.print_json(json_text)
    else:
        output.write_text(json_text + "\n", encoding="utf-8")
        console.print(f"wrote {output}")


@app.command()
def score(
    results: Path = typer.Option(..., "--results", "-r", exists=True, readable=True),
) -> None:
    """Print a summary of a ``results.jsonl`` file produced by ``compactbench run``."""
    from rich.table import Table

    from compactbench.runner import to_run_result

    try:
        run_result = to_run_result(results)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    header = Table(title="Run")
    header.add_column("Field")
    header.add_column("Value")
    header.add_row("run_id", run_result.run_id)
    header.add_row("method", f"{run_result.method_name} ({run_result.method_version})")
    header.add_row("suite", f"{run_result.suite_key} ({run_result.suite_version})")
    header.add_row("target", f"{run_result.target_provider} / {run_result.target_model}")
    header.add_row("scorer", run_result.scorer_version)
    header.add_row("started", run_result.started_at.isoformat())
    header.add_row("completed", run_result.completed_at.isoformat())
    console.print(header)

    per_case = Table(title=f"{len(run_result.cases)} case(s)")
    per_case.add_column("Case ID")
    per_case.add_column("Case score", justify="right")
    per_case.add_column("Drift resistance", justify="right")
    per_case.add_column("Cycles", justify="right")
    for case in run_result.cases:
        per_case.add_row(
            case.case_id,
            f"{case.case_score:.3f}",
            f"{case.drift_resistance:.3f}",
            str(len(case.cycles)),
        )
    console.print(per_case)

    summary = Table(title="Aggregate")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("overall_score", f"{run_result.overall_score:.3f}")
    summary.add_row("drift_resistance", f"{run_result.drift_resistance:.3f}")
    summary.add_row("constraint_retention", f"{run_result.constraint_retention:.3f}")
    summary.add_row("contradiction_rate", f"{run_result.contradiction_rate:.3f}")
    summary.add_row("compression_ratio", f"{run_result.compression_ratio:.2f}x")
    console.print(summary)

    for note in run_result.notes:
        console.print(f"[yellow]note: {note}[/yellow]")


@app.command()
def submit(
    results: Path = typer.Option(
        ...,
        "--results",
        "-r",
        exists=True,
        readable=True,
        help="Local results.jsonl produced by `compactbench run`.",
    ),
    handle: str = typer.Option(..., "--handle", help="Your GitHub handle."),
    method_name: str = typer.Option(
        ..., "--name", help="Method name in kebab-case, e.g. 'my-ledger-v1'."
    ),
) -> None:
    """Print the steps to submit a method for leaderboard scoring.

    Full automation of PR creation is out of scope for the local CLI — GitHub
    Actions evaluation happens against the hidden test set on a repo secret,
    so submission is always a PR + maintainer review. This command prints a
    checklist so you don't miss a step.
    """
    method_dir = Path("submissions") / handle / method_name
    console.print("[bold]Submit a method to the CompactBench leaderboard[/bold]")
    console.print("")
    console.print(f"  1. Create [cyan]{method_dir}/[/cyan] in your fork.")
    console.print(
        f"  2. Copy the scaffold from [cyan]submissions/_template/[/cyan] "
        f"into [cyan]{method_dir}/[/cyan] and edit every file."
    )
    console.print(
        f"  3. Put your validated [cyan]{results}[/cyan] at "
        f"[cyan]{method_dir}/results.jsonl[/cyan]."
    )
    console.print(
        "  4. Commit, push, and open a PR on https://github.com/compactbench/compactbench"
    )
    console.print(
        "  5. A maintainer will code-review and apply the [cyan]evaluate[/cyan] "
        "label, which runs your method against the hidden set."
    )
    console.print("")
    console.print("Full protocol: https://compactbench.github.io/compactbench/submitting/")


providers_app = typer.Typer(help="Inspect available model providers.", no_args_is_help=True)
suites_app = typer.Typer(help="Inspect available benchmark suites.", no_args_is_help=True)
app.add_typer(providers_app, name="providers")
app.add_typer(suites_app, name="suites")


@providers_app.command("list")
def providers_list() -> None:
    """List registered model providers."""
    from rich.table import Table

    from compactbench.providers import list_providers

    providers = list_providers()
    if not providers:
        console.print("[yellow]no providers registered[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title="Model providers")
    table.add_column("Key")
    table.add_column("Notes")
    notes: dict[str, str] = {
        "mock": "deterministic, offline — for tests and local dev",
        "groq": "Groq Cloud. Set COMPACTBENCH_GROQ_API_KEY.",
        "google-ai-studio": ("Google AI Studio. Set COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY."),
        "ollama": "Local Ollama. COMPACTBENCH_OLLAMA_BASE_URL (default localhost:11434).",
    }
    for key in providers:
        table.add_row(key, notes.get(key, ""))
    console.print(table)


@suites_app.command("list")
def suites_list(
    benchmarks_dir: Path = typer.Option(
        default_benchmarks_dir(),
        "--benchmarks-dir",
        help="Directory containing public benchmark suites.",
    ),
) -> None:
    """List available benchmark suites."""
    from rich.table import Table

    from compactbench.dsl import TemplateError, load_suite, validate_template

    if not benchmarks_dir.is_dir():
        console.print(f"[yellow]no benchmarks directory at {benchmarks_dir}[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title="Benchmark suites")
    table.add_column("Suite")
    table.add_column("Templates", justify="right")
    table.add_column("Families")

    found_any = False
    for suite_path in sorted(p for p in benchmarks_dir.iterdir() if p.is_dir()):
        try:
            templates = load_suite(suite_path)
            for t in templates:
                validate_template(t)
        except TemplateError as exc:
            console.print(f"[red]{suite_path.name}: {exc}[/red]")
            continue
        families = sorted({t.family for t in templates})
        table.add_row(suite_path.name, str(len(templates)), ", ".join(families) or "—")
        found_any = True

    if not found_any:
        console.print(f"[yellow]no suites found under {benchmarks_dir}[/yellow]")
        raise typer.Exit(code=1)

    console.print(table)
