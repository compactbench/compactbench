"""CompactBench command-line interface.

Implemented incrementally. Each command raises ``NotImplementedError`` until its
backing workorder lands. See docs/architecture/workorders.md.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from compactbench import __version__

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
        ..., "--method", "-m", help="Method id: 'built-in:<key>' or path:ClassName."
    ),
    suite: str = typer.Option("starter", "--suite", "-s", help="Benchmark suite key."),
    provider: str = typer.Option("mock", "--provider", "-p", help="Model provider key."),
    model: str = typer.Option("mock-deterministic", "--model", help="Provider-specific model key."),
    drift_cycles: int = typer.Option(2, "--drift-cycles", min=0, max=5),
    seed_group: str = typer.Option("default", "--seed-group"),
    output: Path = typer.Option(Path("results.jsonl"), "--output", "-o"),
) -> None:
    """Run a compaction method against a benchmark suite."""
    raise NotImplementedError("run: implemented in WO-007")


@app.command()
def generate(
    template: str = typer.Option(..., "--template", "-t", help="Template key."),
    seed: int = typer.Option(0, "--seed"),
    difficulty: str = typer.Option("medium", "--difficulty"),
) -> None:
    """Generate a single benchmark case from a template and seed."""
    raise NotImplementedError("generate: implemented in WO-003")


@app.command()
def score(
    results: Path = typer.Option(..., "--results", "-r", exists=True, readable=True),
) -> None:
    """Score a results.jsonl file produced by a prior run."""
    raise NotImplementedError("score: implemented in WO-004")


@app.command()
def submit(
    results: Path = typer.Option(..., "--results", "-r", exists=True, readable=True),
) -> None:
    """Open a PR to submit results for leaderboard scoring."""
    raise NotImplementedError("submit: implemented in WO-008")


providers_app = typer.Typer(help="Inspect available model providers.", no_args_is_help=True)
suites_app = typer.Typer(help="Inspect available benchmark suites.", no_args_is_help=True)
app.add_typer(providers_app, name="providers")
app.add_typer(suites_app, name="suites")


@providers_app.command("list")
def providers_list() -> None:
    """List configured model providers."""
    raise NotImplementedError("providers list: implemented in WO-006")


@suites_app.command("list")
def suites_list(
    benchmarks_dir: Path = typer.Option(
        Path("benchmarks/public"),
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
