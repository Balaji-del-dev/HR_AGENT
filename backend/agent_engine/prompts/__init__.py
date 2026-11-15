"""Versioned prompt templates.

Templates live in Git (templates/<name>.system.j2 and <name>.user.j2) and are
changed through pull requests and the eval gate. ``sync_prompts`` records each
distinct template text as a PromptVersion row; every agent run stores the
name@version of each prompt it used.
"""

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(  # noqa: S701 - prompts are plain text, never HTML
    loader=FileSystemLoader(TEMPLATE_DIR), undefined=StrictUndefined, keep_trailing_newline=False
)
_labels: dict[str, str] = {}


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    sha256: str

    @property
    def label(self) -> str:
        return _labels.get(self.name, f"{self.name}@{self.sha256[:8]}")

    def render(self, data: dict[str, Any], **extra: Any) -> list[BaseMessage]:
        messages: list[BaseMessage] = [
            SystemMessage(_env.get_template(f"{self.name}.system.j2").render(data=data, **extra))
        ]
        if (TEMPLATE_DIR / f"{self.name}.user.j2").exists():
            messages.append(HumanMessage(_env.get_template(f"{self.name}.user.j2").render(data=data, **extra)))
        return messages

    def system(self, **extra: Any) -> str:
        return _env.get_template(f"{self.name}.system.j2").render(data={}, **extra)


def prompt_names() -> list[str]:
    return sorted({path.name.split(".")[0] for path in TEMPLATE_DIR.glob("*.system.j2")})


def _source(name: str) -> str:
    parts = [(TEMPLATE_DIR / f"{name}.system.j2").read_text()]
    user = TEMPLATE_DIR / f"{name}.user.j2"
    if user.exists():
        parts.append(user.read_text())
    parts.append((TEMPLATE_DIR / "_data_rules.j2").read_text())
    return "\n---\n".join(parts)


@lru_cache(maxsize=64)
def get_prompt(name: str) -> Prompt:
    return Prompt(name=name, sha256=hashlib.sha256(_source(name).encode()).hexdigest())


def sync_prompts() -> dict[str, str]:
    """Record new template versions. Idempotent; safe to call at the start of every run."""
    from django.db import IntegrityError, transaction
    from django.db.models import Max

    from apps.agents.models import PromptVersion

    for name in prompt_names():
        prompt = get_prompt(name)
        existing = PromptVersion.objects.filter(name=name, sha256=prompt.sha256).first()
        if existing is None:
            try:
                with transaction.atomic():
                    latest = PromptVersion.objects.filter(name=name).aggregate(v=Max("version"))["v"] or 0
                    existing = PromptVersion.objects.create(
                        name=name, version=latest + 1, sha256=prompt.sha256, template=_source(name)
                    )
            except IntegrityError:
                existing = PromptVersion.objects.get(name=name, sha256=prompt.sha256)
        _labels[name] = f"{name}@{existing.version}"
    return dict(_labels)
