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
    benchmarks_dir: Path = typer.Option(
        Path("benchmarks/public"),
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
    """Score a JSONL file of ``{case, artifact, responses}`` records.

    Each line must contain a ``GeneratedCase`` at ``case``, a
    ``CompactionArtifact`` at ``artifact``, and a mapping from evaluation item
    key to model-response string at ``responses``. Optional ``cycle_number``
    is passed through.
    """
    import json

    from rich.table import Table

    from compactbench.contracts import CompactionArtifact, GeneratedCase
    from compactbench.scoring import ScoringError, score_cycle

    scorecards: list[tuple[str, Any]] = []
    with results.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
                case = GeneratedCase.model_validate(record["case"])
                artifact = CompactionArtifact.model_validate(record["artifact"])
                responses: dict[str, str] = record["responses"]
                cycle_num = int(record.get("cycle_number", 0))
                sc = score_cycle(case, artifact, responses, cycle_number=cycle_num)
            except (KeyError, ScoringError, ValueError) as exc:
                console.print(f"[red]line {line_num}: {exc}[/red]")
                raise typer.Exit(code=1) from exc
            scorecards.append((case.case_id, sc))

    if not scorecards:
        console.print("[yellow]no records scored[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title=f"Scored {len(scorecards)} case(s)")
    table.add_column("Case ID")
    table.add_column("Cycle score", justify="right")
    table.add_column("Penalized", justify="right")
    table.add_column("Contradiction", justify="right")
    table.add_column("Compression", justify="right")
    for case_id, sc in scorecards:
        table.add_row(
            case_id,
            f"{sc.cycle_score:.3f}",
            f"{sc.penalized_cycle_score:.3f}",
            f"{sc.contradiction_rate:.3f}",
            f"{sc.compression_ratio:.2f}x",
        )
    console.print(table)

    scores = [sc.cycle_score for _, sc in scorecards]
    penalized = [sc.penalized_cycle_score for _, sc in scorecards]
    compressions = [sc.compression_ratio for _, sc in scorecards]
    console.print("")
    console.print("[bold]Aggregate[/bold]")
    console.print(f"  mean cycle score:   {sum(scores) / len(scores):.3f}")
    console.print(f"  mean penalized:     {sum(penalized) / len(penalized):.3f}")
    console.print(f"  mean compression:   {sum(compressions) / len(compressions):.2f}x")


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
