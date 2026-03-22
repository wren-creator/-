#!/usr/bin/env python3
"""LLM Validator CLI; investigate and validate language models."""

import sys
import json
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich import print as rprint

from runner import Runner

app = typer.Typer(
    name="llm-validator",
    help="Validate and investigate LLMs using structured test suites.",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    suite: Path = typer.Argument(..., help="Path to YAML/JSON test suite file"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override the model specified in the suite"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write detailed log to a JSON file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full prompts and responses for every test"),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop on first test failure"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags to filter tests (e.g. safety,factual)"),
    skip_health_check: bool = typer.Option(False, "--skip-health-check", help="Skip adapter connectivity check before running"),
):
    """Run a test suite against an LLM and report results."""
    if not suite.exists():
        console.print(f"[red]Error:[/red] Suite file not found: {suite}")
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold cyan]LLM Validator[/bold cyan]\n[dim]Suite:[/dim] {suite}",
        border_style="cyan"
    ))

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    runner = Runner(
        suite_path=suite,
        model_override=model,
        output_path=output,
        verbose=verbose,
        fail_fast=fail_fast,
        tags=tag_list,
        skip_health_check=skip_health_check,
    )

    success = runner.run()
    raise typer.Exit(0 if success else 1)


@app.command()
def validate(
    suite: Path = typer.Argument(..., help="Path to YAML/JSON test suite file"),
):
    """Validate a test suite file without running it."""
    from schemas.loader import load_and_validate_suite
    try:
        suite_data = load_and_validate_suite(suite)
        console.print(f"[green]✓[/green] Suite is valid: [bold]{suite_data.suite}[/bold]")
        console.print(f"  [dim]{len(suite_data.tests)} test(s) defined[/dim]")
    except Exception as e:
        console.print(f"[red]✗ Validation failed:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def list_models():
    """List supported model providers and example model strings."""
    console.print(Panel.fit(
        "[bold]Supported Providers via LiteLLM[/bold]\n\n"
        "[cyan]OpenAI:[/cyan]       gpt-4o, gpt-4o-mini, gpt-3.5-turbo\n"
        "[cyan]Anthropic:[/cyan]    claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001\n"
        "[cyan]Ollama:[/cyan]       ollama/llama3, ollama/mistral\n"
        "[cyan]Mistral:[/cyan]      mistral/mistral-large-latest\n"
        "[cyan]Gemini:[/cyan]       gemini/gemini-1.5-pro\n\n"
        "[dim]Set your API keys via environment variables:\n"
        "OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, etc.[/dim]",
        border_style="cyan"
    ))


@app.command(name="model-info")
def model_info(
    model: str = typer.Argument(..., help="Model string, e.g. gpt-4o or ollama/llama3"),
):
    """Show creator, parameter count, architecture, and cost info for a model."""
    from model_registry import lookup
    from rich.table import Table

    meta = lookup(model)

    # Try to get live token/cost info from LiteLLM
    litellm_info = {}
    try:
        import litellm
        litellm_info = litellm.get_model_info(model) or {}
    except Exception:
        pass

    # ── Header panel ──────────────────────────────────────────────────────
    if meta:
        open_tag = "[green]Yes — weights publicly available[/green]" if meta.open_weights else "[yellow]No — proprietary[/yellow]"
        header = (
            f"[bold cyan]{model}[/bold cyan]\n"
            f"[dim]Family:[/dim] {meta.family}  |  "
            f"[dim]Released:[/dim] {meta.release_year}  |  "
            f"[dim]Open weights:[/dim] {open_tag}"
        )
    else:
        header = f"[bold cyan]{model}[/bold cyan]\n[dim]Not found in local registry — showing LiteLLM data only[/dim]"

    console.print(Panel.fit(header, border_style="cyan", title="Model Info"))
    console.print()

    # ── Main info table ───────────────────────────────────────────────────
    table = Table(show_header=False, border_style="dim", padding=(0, 2))
    table.add_column("Field", style="dim", width=22)
    table.add_column("Value")

    if meta:
        table.add_row("Creator", f"[bold]{meta.creator}[/bold]")
        table.add_row("Model family", meta.family)
        table.add_row("Architecture", meta.architecture)
        table.add_row("License", meta.license)

        # Parameter count with confidence note
        param_display = meta.parameters if meta.parameters else "[italic red]Not disclosed[/italic red]"
        table.add_row("Parameter count", param_display)
        table.add_row("  ↳ source/confidence", f"[dim]{meta.parameters_note}[/dim]")

        if meta.hf_url:
            table.add_row("HuggingFace", f"[link={meta.hf_url}]{meta.hf_url}[/link]")

        if meta.notes:
            table.add_row("Notes", f"[dim]{meta.notes}[/dim]")

    # LiteLLM live data
    if litellm_info:
        console.print(table)
        console.print()

        cost_table = Table(show_header=False, border_style="dim", padding=(0, 2), title="Context & Pricing (LiteLLM)")
        cost_table.add_column("Field", style="dim", width=22)
        cost_table.add_column("Value")

        provider = litellm_info.get("litellm_provider") or (meta.creator if meta else "—")
        cost_table.add_row("Provider (LiteLLM)", str(provider))

        max_in = litellm_info.get("max_input_tokens")
        max_out = litellm_info.get("max_output_tokens")
        if max_in:
            cost_table.add_row("Max input tokens", f"{max_in:,}")
        if max_out:
            cost_table.add_row("Max output tokens", f"{max_out:,}")

        in_cost = litellm_info.get("input_cost_per_token")
        out_cost = litellm_info.get("output_cost_per_token")
        if in_cost is not None:
            cost_table.add_row("Input cost", f"${in_cost * 1_000_000:.4f} / 1M tokens")
        if out_cost is not None:
            cost_table.add_row("Output cost", f"${out_cost * 1_000_000:.4f} / 1M tokens")

        console.print(cost_table)
    else:
        if not meta:
            console.print("[yellow]Model not found in registry and LiteLLM returned no info.[/yellow]")
            console.print(f"[dim]Try: python cli.py browse-models  — to see all known models[/dim]")
        else:
            console.print(table)
            console.print()
            console.print("[dim]No LiteLLM pricing data available for this model (may be local/Ollama).[/dim]")

    # Weights disclaimer
    console.print()
    if meta and not meta.open_weights:
        console.print(
            "[dim]⚠  Parameter counts for closed models are not officially published. "
            "Figures marked as estimates are based on community research and may be inaccurate.[/dim]"
        )


@app.command(name="browse-models")
def browse_models(
    creator: Optional[str] = typer.Option(None, "--creator", "-c", help="Filter by creator (e.g. Meta, OpenAI)"),
    open_only: bool = typer.Option(False, "--open", help="Show only open-weights models"),
):
    """Browse all models in the registry with their key metadata."""
    from model_registry import all_models
    from rich.table import Table

    rows = all_models()

    if creator:
        rows = [(k, v) for k, v in rows if creator.lower() in v.creator.lower()]
    if open_only:
        rows = [(k, v) for k, v in rows if v.open_weights]

    if not rows:
        console.print("[yellow]No models matched your filters.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"Model Registry ({len(rows)} models)", border_style="dim")
    table.add_column("Model string", style="cyan", no_wrap=True)
    table.add_column("Creator", style="bold")
    table.add_column("Parameters")
    table.add_column("Open weights")
    table.add_column("License")
    table.add_column("Year", justify="right")

    for key, meta in rows:
        params = meta.parameters or "[dim]undisclosed[/dim]"
        open_tag = "[green]✓[/green]" if meta.open_weights else "[red]✗[/red]"
        table.add_row(key, meta.creator, params, open_tag, meta.license, str(meta.release_year))

    console.print(table)
    console.print(f"\n[dim]Run [bold]python cli.py model-info <model>[/bold] for full details on any model.[/dim]")


@app.command(name="checksum")
def checksum_cmd(
    model: str = typer.Argument(..., help="Model string, e.g. gpt-4o or ollama/llama3"),
    ledger: Path = typer.Option(Path("checksum_ledger.json"), "--ledger", "-l", help="Path to checksum ledger file"),
    hf_path: Optional[str] = typer.Option(None, "--hf-path", help="Local HuggingFace model directory path"),
    export: Optional[Path] = typer.Option(None, "--export", "-o", help="Export this run's result to a JSON file"),
):
    """
    Compute and record a checksum for a model.

    \b
    Open/local models  → SHA-256 hash of weight files on disk
    Closed API models  → Behavioural fingerprint (deterministic probe suite)

    Re-run at any time to detect if the model has changed.
    """
    from checksum import compute_checksum
    from rich.table import Table

    console.print(Panel.fit(
        f"[bold cyan]Model Checksum[/bold cyan]\n[dim]Model:[/dim] {model}",
        border_style="cyan"
    ))
    console.print()

    with console.status("[dim]Computing checksum...[/dim]"):
        result = compute_checksum(model=model, ledger_path=ledger, hf_path=hf_path)

    console.print()

    # ── Result panel ──────────────────────────────────────────────────────
    strategy_label = {
        "weight_hash": "[green]Weight hash[/green] (SHA-256 of model files)",
        "behavioural_fingerprint": "[yellow]Behavioural fingerprint[/yellow] (deterministic probe suite)",
    }.get(result["strategy"], result["strategy"])

    table = Table(show_header=False, border_style="dim", padding=(0, 2))
    table.add_column("Field", style="dim", width=22)
    table.add_column("Value")

    table.add_row("Model", f"[bold]{result['model']}[/bold]")
    table.add_row("Strategy", strategy_label)
    table.add_row("Checksum", f"[bold green]{result['checksum']}[/bold green]" if result["checksum"] else "[red]Failed[/red]")
    table.add_row("Timestamp", result["timestamp"])
    table.add_row("Ledger", str(ledger))

    if result["previous_checksum"]:
        if result["changed"]:
            table.add_row("Previous checksum", f"[dim]{result['previous_checksum']}[/dim]")
            table.add_row("Changed?", "[bold red]⚠  YES — checksum differs from last run[/bold red]")
        else:
            table.add_row("Changed?", "[green]✓  No change detected[/green]")
    else:
        table.add_row("Changed?", "[dim]First run — baseline recorded[/dim]")

    console.print(table)

    # ── Probe details (behavioural) ───────────────────────────────────────
    if result["strategy"] == "behavioural_fingerprint":
        probes = result["detail"].get("probe_responses", [])
        errors = result["detail"].get("errors", [])

        console.print()
        probe_table = Table(title="Probe Responses", border_style="dim")
        probe_table.add_column("Probe ID", style="cyan", width=14)
        probe_table.add_column("Response")

        for p in probes:
            resp = p["response"]
            display = f"[red]ERROR: {resp}[/red]" if resp.startswith("ERROR:") else resp
            probe_table.add_row(p["probe_id"], display)

        console.print(probe_table)

        if errors:
            console.print(f"\n[red]{len(errors)} probe(s) failed.[/red] Results may be incomplete.")

        console.print()
        console.print(
            "[dim]Note: Behavioural fingerprints detect model version changes and silent updates "
            "but cannot verify weight-level identity for closed models.[/dim]"
        )

    # ── File hashes (weight hash) ─────────────────────────────────────────
    elif result["strategy"] == "weight_hash":
        files = result["detail"].get("files", {})
        if files:
            console.print()
            file_table = Table(title="File Hashes", border_style="dim")
            file_table.add_column("File / Digest", style="cyan")
            file_table.add_column("SHA-256")
            for name, h in files.items():
                short_name = name if len(name) <= 40 else name[:18] + "…" + name[-18:]
                file_table.add_row(short_name, h)
            console.print(file_table)

    # ── Export ────────────────────────────────────────────────────────────
    if export:
        export.parent.mkdir(parents=True, exist_ok=True)
        export.write_text(json.dumps(result, indent=2))
        console.print(f"\n[dim]Result exported to:[/dim] {export}")

    # Exit with code 2 if checksum changed (useful in CI)
    if result["changed"]:
        raise typer.Exit(2)


@app.command(name="checksum-history")
def checksum_history(
    model: Optional[str] = typer.Argument(None, help="Model to show history for (omit for all models)"),
    ledger: Path = typer.Option(Path("checksum_ledger.json"), "--ledger", "-l", help="Path to checksum ledger file"),
):
    """Show the checksum history for a model (or all models) from the ledger."""
    from checksum import get_history, get_all_history
    from rich.table import Table

    if model:
        history = get_history(model, ledger_path=ledger)
        if not history:
            console.print(f"[yellow]No history found for '{model}' in {ledger}[/yellow]")
            raise typer.Exit(0)

        table = Table(title=f"Checksum History: {model}", border_style="dim")
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("Timestamp")
        table.add_column("Checksum")
        table.add_column("Strategy")
        table.add_column("Changed?")

        prev = None
        for i, entry in enumerate(history):
            chk = entry.get("checksum", "—")
            changed = ""
            if prev is not None:
                if chk != prev:
                    changed = "[bold red]⚠ CHANGED[/bold red]"
                else:
                    changed = "[green]same[/green]"
            else:
                changed = "[dim]baseline[/dim]"
            table.add_row(str(i + 1), entry["timestamp"], chk or "—", entry.get("strategy", "—"), changed)
            prev = chk

        console.print(table)

    else:
        all_history = get_all_history(ledger_path=ledger)
        if not all_history:
            console.print(f"[yellow]No entries found in {ledger}[/yellow]")
            raise typer.Exit(0)

        table = Table(title="All Checksum Records", border_style="dim")
        table.add_column("Model", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Latest checksum")
        table.add_column("Latest run")
        table.add_column("Stable?")

        for mdl, entries in sorted(all_history.items()):
            latest = entries[-1]
            checksums = [e.get("checksum") for e in entries]
            stable = len(set(checksums)) == 1
            stable_tag = "[green]✓ stable[/green]" if stable else f"[red]⚠ {len(set(checksums))} distinct values[/red]"
            table.add_row(
                mdl,
                str(len(entries)),
                (latest.get("checksum") or "—")[:16] + "…",
                latest["timestamp"][:19].replace("T", " "),
                stable_tag,
            )

        console.print(table)
        console.print(f"\n[dim]Run [bold]python cli.py checksum-history <model>[/bold] for full history of a specific model.[/dim]")


if __name__ == "__main__":
    app()
