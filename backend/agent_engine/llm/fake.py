"""A chat model that answers from code: offline heuristics by default, test scripts on top.

``script("ResumeExtraction", fn)`` makes every structured call for that schema
return ``fn(messages)``. ``script("chat", fn)`` handles plain and tool-calling
calls. Unscripted calls use agent_engine.llm.heuristics, which read the same
prompt data a real model would.
"""

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel

Responder = Callable[[list[BaseMessage]], Any]
_scripts: dict[str, Responder] = {}
calls: list[tuple[str, list[BaseMessage]]] = []  # every call, for assertions


def script(name: str, responder: Responder) -> None:
    _scripts[name] = responder


def reset() -> None:
    _scripts.clear()
    calls.clear()


@contextmanager
def scripted(**responders: Responder) -> Iterator[None]:
    previous = dict(_scripts)
    _scripts.update(responders)
    try:
        yield
    finally:
        _scripts.clear()
        _scripts.update(previous)


def _approx_tokens(messages: Sequence[BaseMessage]) -> int:
    return sum(len(str(m.content)) for m in messages) // 4 + 1


def _respond(name: str, messages: list[BaseMessage], tools: list[dict[str, Any]] | None = None) -> Any:
    from agent_engine.llm import heuristics

    calls.append((name, messages))
    responder = _scripts.get(name)
    if responder is not None:
        return responder(messages)
    return heuristics.respond(name, messages, tools or [])


class ScriptedChatModel(BaseChatModel):
    model_name: str = "offline"
    bound_tools: list[dict[str, Any]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        schema_name = kwargs.get("schema_name")
        if schema_name:
            data = _respond(schema_name, messages)
            if isinstance(data, BaseModel):
                data = data.model_dump()
            message = AIMessage(content=json.dumps(data))
        else:
            out = _respond("chat", messages, self.bound_tools)
            message = out if isinstance(out, AIMessage) else AIMessage(content=str(out))
        tokens_in = _approx_tokens(messages)
        tokens_out = max(1, len(str(message.content)) // 4)
        message.usage_metadata = {
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        }
        message.response_metadata = {"model_name": self.model_name}
        if run_manager and isinstance(message.content, str):
            run_manager.on_llm_new_token(message.content)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable[LanguageModelInput, AIMessage]:
        converted = [convert_to_openai_tool(tool) for tool in tools]
        return self.model_copy(update={"bound_tools": converted})

    def with_structured_output(  # type: ignore[override]
        self, schema: type[BaseModel], *, method: str = "json_schema", include_raw: bool = False, **kwargs: Any
    ) -> Runnable[LanguageModelInput, BaseModel]:
        bound = self.bind(schema_name=schema.__name__)

        def parse(message: AIMessage) -> BaseModel:
            return schema.model_validate_json(str(message.content))

        return bound | RunnableLambda(parse)
