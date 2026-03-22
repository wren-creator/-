#!/usr/bin/env python3

"""Core runner; loads a suite, calls the model, evaluates responses."""

import time
from pathlib import Path
from typing import List, Optional, Set

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from schemas.loader import load_and_validate_suite, TestCase, TestSuite
from adapters.base import BaseAdapter, CompletionResponse, AdapterError
from adapters.litellm_adapter import LiteLLMAdapter
from evaluators.accuracy import AccuracyEvaluator
from evaluators.safety import SafetyEvaluator
from evaluators.consistency import ConsistencyEvaluator
from reporters.detailed_log import DetailedLogger

console = Console()

EVALUATOR_MAP = {
    "accuracy": AccuracyEvaluator,
    "safety": SafetyEvaluator,
    "consistency": ConsistencyEvaluator,
}


class Runner:
    def __init__(
        self,
        suite_path: Path,
        model_override: Optional[str] = None,
        output_path: Optional[Path] = None,
        verbose: bool = False,
        fail_fast: bool = False,
        tags: Optional[List[str]] = None,
        skip_health_check: bool = False,
    ):
        """
        Args:
            suite_path:        Path to the YAML/JSON test suite.
            model_override:    Model string to use instead of the one in the suite.
            output_path:       Write a detailed JSON log to this path when done.
            verbose:           Print full prompts and responses for every test.
            fail_fast:         Stop the run on the first test failure.
            tags:              Only run tests whose tags include at least one of these.
            skip_health_check: Skip the adapter connectivity check before running.
        """
        self.suite_path = suite_path
        self.model_override = model_override
        self.output_path = output_path
        self.verbose = verbose
        self.fail_fast = fail_fast
        self.tags: Set[str] = set(tags) if tags else set()
        self.skip_health_check = skip_health_check

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> bool:
        """
        Execute the suite. Returns True if all tests pass, False otherwise.
        Writes a detailed log to output_path if set.
        """
        # 1. Load and validate suite
        try:
            suite: TestSuite = load_and_validate_suite(self.suite_path)
        except Exception as e:
            console.print(f"[red]Failed to load suite:[/red] {e}")
            return False

        model = self.model_override or suite.model

        # 2. Filter tests by tag if requested
        tests = self._filter_tests(suite.tests)
        if not tests:
            console.print("[yellow]No tests matched the specified tags. Nothing to run.[/yellow]")
            return True

        console.print(
            f"[dim]Model:[/dim] [bold]{model}[/bold]  |  "
            f"[dim]Tests:[/dim] {len(tests)}"
            + (f"  |  [dim]Tags:[/dim] {', '.join(self.tags)}" if self.tags else "")
            + "\n"
        )

        # 3. Build adapter
        adapter = LiteLLMAdapter(model=model)

        # 4. Health check
        if not self.skip_health_check:
            if not self._health_check(adapter):
                return False

        # 5. Run tests
        logger = DetailedLogger()
        passed = failed = skipped = 0
        stop = False

        for test in tests:
            if stop:
                skipped += 1
                continue

            system = test.system_prompt or suite.default_system_prompt
            evaluators = test.parsed_evaluators()

            if not evaluators:
                console.print(f"  [yellow]⚠[/yellow] [bold]{test.id}[/bold] — no evaluators defined, skipping.")
                skipped += 1
                continue

            # Split evaluators: consistency needs N runs, others need 1
            consistency_evals = [e for e in evaluators if e.type == "consistency"]
            single_evals      = [e for e in evaluators if e.type != "consistency"]

            test_passed = True

            # -- Single-run evaluators (accuracy, safety) --
            if single_evals:
                response, elapsed, error = self._call_model(adapter, test, system)
                text = response.text if response else ""
                tokens = self._token_summary(response)

                eval_results = self._run_single_evaluators(single_evals, text, error)
                all_passed = all(r["passed"] for r in eval_results)
                test_passed = test_passed and all_passed

                self._print_single_result(test, text, eval_results, elapsed, tokens, all_passed, error)
                logger.record(test, text, eval_results, elapsed, error)

                if not all_passed:
                    failed += 1
                    if self.fail_fast:
                        console.print("[yellow]Stopping early (--fail-fast)[/yellow]\n")
                        stop = True
                        continue
                else:
                    passed += 1

            # -- Consistency evaluators (multiple runs) --
            for cons_config in consistency_evals:
                responses, errors = self._call_model_n(adapter, test, system, cons_config.runs)
                texts = [r.text if r else "" for r in responses]

                ev = ConsistencyEvaluator()
                result = ev.evaluate(texts, cons_config)
                test_passed = test_passed and result["passed"]

                self._print_consistency_result(test, texts, result, errors)
                logger.record(test, texts, [result], 0, errors[0] if errors else None)

                if result["passed"]:
                    passed += 1
                else:
                    failed += 1
                    if self.fail_fast:
                        console.print("[yellow]Stopping early (--fail-fast)[/yellow]\n")
                        stop = True

        # 6. Summary
        self._print_summary(passed, failed, skipped)

        # 7. Write log
        if self.output_path:
            logger.write(self.output_path)
            console.print(f"[dim]Detailed log written to:[/dim] {self.output_path}")

        return failed == 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _filter_tests(self, tests: List[TestCase]) -> List[TestCase]:
        """Return only tests that match the requested tags (if any)."""
        if not self.tags:
            return tests
        return [t for t in tests if self.tags.intersection(set(t.tags))]

    def _health_check(self, adapter: BaseAdapter) -> bool:
        """Run adapter health check and report. Returns False if unhealthy."""
        with console.status("[dim]Checking model connectivity...[/dim]"):
            status = adapter.health_check()

        if status.ok:
            console.print(f"[green]✓[/green] Model reachable  [dim]({status.latency_ms:.0f}ms)[/dim]\n")
            return True
        else:
            console.print(f"[red]✗ Health check failed:[/red] {status.error}")
            console.print("[dim]Use --skip-health-check to run anyway.[/dim]\n")
            return False

    def _call_model(
        self,
        adapter: BaseAdapter,
        test: TestCase,
        system: Optional[str],
    ):
        """
        Call the model once for a test. Returns (CompletionResponse | None, elapsed_s, error | None).
        Uses the latency recorded by the adapter rather than a separate timer.
        """
        with Progress(
            SpinnerColumn(),
            TextColumn(f"  [cyan]{test.id}[/cyan] ..."),
            transient=True,
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            start = time.monotonic()
            try:
                response: CompletionResponse = adapter.complete(
                    prompt=test.prompt,
                    system=system,
                )
                elapsed = response.latency_ms / 1000  # use adapter-recorded latency
                return response, elapsed, None
            except AdapterError as e:
                elapsed = time.monotonic() - start
                return None, elapsed, str(e)
            except Exception as e:
                elapsed = time.monotonic() - start
                return None, elapsed, f"Unexpected error: {e}"

    def _call_model_n(
        self,
        adapter: BaseAdapter,
        test: TestCase,
        system: Optional[str],
        n: int,
    ):
        """
        Call the model n times for a consistency test.
        Returns (list[CompletionResponse | None], list[str errors]).
        """
        responses = []
        errors = []
        console.print(f"  [dim]Consistency — running {n}×:[/dim] [cyan]{test.id}[/cyan]")

        for i in range(n):
            try:
                resp = adapter.complete(prompt=test.prompt, system=system)
                responses.append(resp)
                errors.append(None)
            except Exception as e:
                responses.append(None)
                errors.append(str(e))

        return responses, errors

    def _run_single_evaluators(self, evaluators, text: str, error: Optional[str]) -> list:
        """Run accuracy/safety evaluators against a single response text."""
        if error:
            return [{"evaluator": "api_call", "passed": False, "reason": error}]

        results = []
        for ev_config in evaluators:
            ev_class = EVALUATOR_MAP[ev_config.type]
            result = ev_class().evaluate(text, ev_config)
            results.append(result)
        return results

    def _token_summary(self, response: Optional[CompletionResponse]) -> str:
        """Format a compact token usage string from a response."""
        if not response or response.total_tokens is None:
            return ""
        parts = []
        if response.prompt_tokens is not None:
            parts.append(f"in={response.prompt_tokens}")
        if response.completion_tokens is not None:
            parts.append(f"out={response.completion_tokens}")
        return f"[dim]tokens: {', '.join(parts)}[/dim]" if parts else ""

    def _print_single_result(
        self,
        test: TestCase,
        text: str,
        eval_results: list,
        elapsed: float,
        tokens: str,
        all_passed: bool,
        error: Optional[str],
    ):
        icon = "[green]✓[/green]" if all_passed else "[red]✗[/red]"
        suffix = f"  {tokens}" if tokens else ""
        console.print(f"  {icon} [bold]{test.id}[/bold]  [dim]({elapsed:.2f}s)[/dim]{suffix}")

        if self.verbose or not all_passed:
            if test.description:
                console.print(f"     [dim]Description:[/dim] {test.description}")
            console.print(f"     [dim]Prompt:[/dim]   {test.prompt[:120]}{'…' if len(test.prompt) > 120 else ''}")
            if error:
                console.print(f"     [red]Error:[/red] {error}")
            else:
                console.print(f"     [dim]Response:[/dim] {text[:300]}{'…' if len(text) > 300 else ''}")
            for r in eval_results:
                ev_icon = "✓" if r["passed"] else "✗"
                color = "green" if r["passed"] else "red"
                console.print(f"     [{color}]{ev_icon}[/{color}] [dim][{r['evaluator']}][/dim] {r['reason']}")
            console.print()

    def _print_consistency_result(
        self,
        test: TestCase,
        texts: List[str],
        result: dict,
        errors: list,
    ):
        icon = "[green]✓[/green]" if result["passed"] else "[red]✗[/red]"
        console.print(f"  {icon} [bold]{test.id}[/bold] [dim](consistency)[/dim]")

        if self.verbose or not result["passed"]:
            actual_errors = [e for e in errors if e]
            if actual_errors:
                console.print(f"     [red]{len(actual_errors)} run(s) failed:[/red] {actual_errors[0]}")
            for i, text in enumerate(texts):
                console.print(f"     [dim]Run {i+1}:[/dim] {text[:150]}{'…' if len(text) > 150 else ''}")
            ev_color = "green" if result["passed"] else "red"
            console.print(f"     [{ev_color}]{'✓' if result['passed'] else '✗'}[/{ev_color}] {result['reason']}")
            console.print()

    def _print_summary(self, passed: int, failed: int, skipped: int):
        console.print()
        table = Table(title="Results", border_style="dim")
        table.add_column("Passed",  style="green", justify="right")
        table.add_column("Failed",  style="red",   justify="right")
        table.add_column("Skipped", style="yellow", justify="right")
        table.add_column("Total",   justify="right")
        table.add_row(str(passed), str(failed), str(skipped), str(passed + failed + skipped))
        console.print(table)
        console.print()

if __name__ == "__main__":
