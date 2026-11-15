"""Model factory, structured output, fallback and tracing callbacks.

Providers (LLM_PROVIDER):
  anthropic  Claude through langchain-anthropic (default model claude-opus-5-5).
  ollama     A local model through langchain-ollama (default qwen2.5:1.5b).
  offline    Deterministic heuristics over the same prompts: no model, no network.
  fake       Like offline, but tests can script any response (agent_engine.llm.fake).

Structured output always uses JSON schema (Anthropic output_config.format,
Ollama format=<schema>), never forced tool choice.
"""

import logging
from functools import lru_cache
from typing import Any
from uuid import UUID

from django.conf import settings
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from agent_engine.budget import UsageCallback

logger = logging.getLogger(__name__)


def _build(provider: str, model: str) -> BaseChatModel:
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        # No temperature: current Claude models reject sampling parameters.
        return ChatAnthropic(  # type: ignore[call-arg]
            model=model or "claude-opus-5-5",
            max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=2,
            reasoning_effort=settings.ANTHROPIC_EFFORT,
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model or "qwen2.5:1.5b",
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0,
            num_ctx=settings.OLLAMA_NUM_CTX,
            keep_alive="10m",
            client_kwargs={"timeout": settings.LLM_TIMEOUT_SECONDS},
        )
    if provider in ("offline", "fake"):
        from agent_engine.llm.fake import ScriptedChatModel

        return ScriptedChatModel(model_name=model or provider)
    raise ValueError(f"Unknown LLM provider {provider!r}")


@lru_cache(maxsize=4)
def get_chat_model() -> BaseChatModel:
    return _build(settings.LLM_PROVIDER, settings.LLM_MODEL)


@lru_cache(maxsize=4)
def get_fallback_model() -> BaseChatModel | None:
    if not settings.LLM_FALLBACK_PROVIDER:
        return None
    return _build(settings.LLM_FALLBACK_PROVIDER, settings.LLM_FALLBACK_MODEL)


def model_label() -> str:
    return f"{settings.LLM_PROVIDER}:{settings.LLM_MODEL}"


def structured_model[SchemaT: BaseModel](schema: type[SchemaT]) -> Runnable[Any, SchemaT]:
    primary = get_chat_model().with_structured_output(schema, method="json_schema")
    fallback = get_fallback_model()
    if fallback is not None:
        primary = primary.with_fallbacks([fallback.with_structured_output(schema, method="json_schema")])
    return primary  # type: ignore[return-value]


def callbacks_for(run_id: UUID) -> list[BaseCallbackHandler]:
    handlers: list[BaseCallbackHandler] = [UsageCallback()]
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        try:
            from langfuse.langchain import CallbackHandler

            handlers.append(CallbackHandler(trace_context={"trace_id": run_id.hex}))
        except Exception:
            logger.warning("Langfuse handler unavailable", exc_info=True)
    return handlers
