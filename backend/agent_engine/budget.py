"""Per-run limits and accounting: tool calls, tokens, prompt versions.

A RunContext is bound for the duration of one execute_run call. LangGraph copies
contextvars into its worker threads, so parallel branches share the same object;
the lock keeps the counters exact.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class BudgetExceeded(Exception):
    """The run hit its tool-call or token budget. It ends with status budget_exceeded."""


@dataclass
class RunContext:
    run_id: UUID
    max_tool_calls: int
    max_tokens: int
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    model_name: str = ""
    prompt_versions: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def charge_tool(self) -> None:
        with self._lock:
            self.tool_calls += 1
            if self.tool_calls > self.max_tool_calls:
                raise BudgetExceeded(f"Tool-call budget of {self.max_tool_calls} reached.")

    def charge_tokens(self, tokens_in: int, tokens_out: int, model_name: str = "") -> None:
        with self._lock:
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out
            if model_name:
                self.model_name = model_name
            if self.tokens_in + self.tokens_out > self.max_tokens:
                raise BudgetExceeded(f"Token budget of {self.max_tokens} reached.")

    def record_prompt(self, name: str, version: str) -> None:
        with self._lock:
            self.prompt_versions[name] = version


_current: ContextVar[RunContext | None] = ContextVar("agent_run_context", default=None)


def current_run() -> RunContext:
    run = _current.get()
    if run is None:
        raise RuntimeError("No agent run is active.")
    return run


def maybe_current_run() -> RunContext | None:
    return _current.get()


@contextmanager
def bind_run(run: RunContext) -> Iterator[RunContext]:
    token = _current.set(run)
    try:
        yield run
    finally:
        _current.reset(token)


class UsageCallback(BaseCallbackHandler):
    """Counts tokens from every LLM call; raising here aborts the run when over budget."""

    raise_error = True

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        run = _current.get()
        if run is None:
            return
        tokens_in = tokens_out = 0
        model_name = ""
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) or {}
                tokens_in += int(usage.get("input_tokens", 0))
                tokens_out += int(usage.get("output_tokens", 0))
                metadata = getattr(message, "response_metadata", None) or {}
                model_name = metadata.get("model_name") or metadata.get("model") or model_name
        run.charge_tokens(tokens_in, tokens_out, model_name)
