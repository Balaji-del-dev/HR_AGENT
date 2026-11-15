"""The LLM eval gate. Exits non-zero when any suite misses its threshold, so CI can block the release."""

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = "Run evaluation suites against the configured LLM provider and store EvalResult rows."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--suite", action="append", choices=["extraction", "matching", "fairness", "redteam"])
        parser.add_argument("--no-store", action="store_true", help="Do not write EvalResult rows.")

    def handle(self, *args: Any, **options: Any) -> None:
        from evals.runner import run_all

        failed = []
        for result in run_all(options["suite"], store=not options["no_store"]):
            status = self.style.SUCCESS("PASS") if result.passed else self.style.ERROR("FAIL")
            self.stdout.write(f"{status} {result.suite}: {json.dumps(result.metrics)} (thresholds {result.thresholds})")
            if not result.passed:
                failed.append(result.suite)
        if failed:
            raise CommandError(f"Eval gate failed: {', '.join(failed)}")
