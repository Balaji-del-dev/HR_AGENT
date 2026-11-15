from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Record the prompt templates in Git as PromptVersion rows."

    def handle(self, *args: Any, **options: Any) -> None:
        from agent_engine.prompts import sync_prompts

        for name, label in sorted(sync_prompts().items()):
            self.stdout.write(f"{name}: {label}")
