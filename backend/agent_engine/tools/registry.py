"""The tool registry: the only way an agent touches platform data.

Each tool wraps service or selector functions. A call:

1. counts against the run's tool budget,
2. checks the calling agent may use the tool,
3. validates arguments with the tool's Pydantic schema,
4. asks the policy engine ``allow(tool, user, resource)``,
5. runs inside the caller's tenant scope (Row-Level Security applies),
6. writes an agent_tool_calls row whatever the outcome.

Identity comes from the ExecutionContext passed by the runtime, never from
arguments. Side-effect tools only create drafts.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError

from agent_engine.bridge import MainThreadBridge
from agent_engine.budget import maybe_current_run
from apps.core.context import ExecutionContext
from apps.core.exceptions import ApplicationError
from apps.core.tenancy import tenant_scope
from policies.engine import decide as policy_decide


class ToolDenied(Exception):
    pass


class ToolInvalid(Exception):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_schema: type[BaseModel]
    func: Callable[[ExecutionContext, Any], Any]
    agents: frozenset[str]
    side_effect: bool = False
    resource: Callable[[ExecutionContext, Any], dict[str, Any]] | None = None
    summarize: Callable[[Any], dict[str, Any]] | None = None


REGISTRY: dict[str, ToolSpec] = {}


def tool(
    name: str,
    *,
    description: str,
    args: type[BaseModel],
    agents: set[str],
    side_effect: bool = False,
    resource: Callable[[ExecutionContext, Any], dict[str, Any]] | None = None,
    summarize: Callable[[Any], dict[str, Any]] | None = None,
) -> Callable[[Callable[[ExecutionContext, Any], Any]], Callable[[ExecutionContext, Any], Any]]:
    def register(func: Callable[[ExecutionContext, Any], Any]) -> Callable[[ExecutionContext, Any], Any]:
        if name in REGISTRY:
            raise ValueError(f"Tool {name} registered twice")
        REGISTRY[name] = ToolSpec(name, description, args, func, frozenset(agents), side_effect, resource, summarize)
        return func

    return register


def _record(
    ctx: ExecutionContext,
    *,
    agent: str,
    name: str,
    arguments: dict[str, Any],
    status: str,
    started: float,
    result: Any = None,
    error: str = "",
    reason: str = "",
    spec: ToolSpec | None = None,
) -> None:
    from apps.agents.models import AgentRun, ToolCall

    if ctx.run_id is None:
        return
    summary: dict[str, Any] = {}
    if result is not None:
        summary = spec.summarize(result) if spec and spec.summarize else _default_summary(result)
    with tenant_scope(ctx.tenant_id):
        ToolCall.objects.create(
            run_id=ctx.run_id,
            tool=name,
            agent=agent,
            arguments=json.loads(json.dumps(arguments, default=str)),
            status=status,
            policy_reason=reason[:200],
            result_summary=summary,
            error=error[:2000],
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        AgentRun.objects.filter(pk=ctx.run_id).update(
            tool_call_count=ToolCall.objects.filter(run_id=ctx.run_id).count()
        )


def _default_summary(result: Any) -> dict[str, Any]:
    if isinstance(result, list):
        return {"items": len(result)}
    if isinstance(result, dict):
        return {"keys": sorted(result)[:20]}
    return {"type": type(result).__name__}


def call_tool(ctx: ExecutionContext, *, agent: str, name: str, **arguments: Any) -> Any:
    """Run one tool for one agent. Must be called from the graph's main thread (it uses the ORM)."""
    started = time.monotonic()
    spec = REGISTRY.get(name)
    run = maybe_current_run()
    if run is not None:
        run.charge_tool()
    if spec is None or agent not in spec.agents:
        reason = f"Agent {agent} may not use {name}."
        _record(ctx, agent=agent, name=name, arguments=arguments, status="denied", started=started, reason=reason)
        raise ToolDenied(reason)
    try:
        args = spec.args_schema(**arguments)
    except ValidationError as exc:
        _record(ctx, agent=agent, name=name, arguments=arguments, status="invalid", started=started, error=str(exc))
        raise ToolInvalid(str(exc)) from exc

    try:
        with tenant_scope(ctx.tenant_id):
            resource = spec.resource(ctx, args) if spec.resource else {}
            verdict = policy_decide(f"tool:{name}", ctx, resource)
            if not verdict.allowed:
                raise ToolDenied(verdict.reason)
            result = spec.func(ctx, args)
    except ToolDenied as exc:
        _record(ctx, agent=agent, name=name, arguments=arguments, status="denied", started=started, reason=str(exc))
        raise
    except ApplicationError as exc:
        _record(ctx, agent=agent, name=name, arguments=arguments, status="error", started=started, error=exc.message)
        raise
    _record(ctx, agent=agent, name=name, arguments=arguments, status="ok", started=started, result=result, spec=spec)
    return result


def langchain_tools(
    ctx: ExecutionContext, *, agent: str, names: list[str], bridge: "MainThreadBridge | None" = None
) -> list[StructuredTool]:
    """Expose registry tools to a LangChain agent loop. ctx is bound here, not passed by the model.

    With a bridge, each call runs on the graph's main thread (see agent_engine.bridge).
    """
    tools = []
    for name in names:
        spec = REGISTRY[name]

        def run(_name: str = name, **kwargs: Any) -> str:
            try:
                if bridge is not None:
                    result = bridge.submit(call_tool, ctx, agent=agent, name=_name, **kwargs)
                else:
                    result = call_tool(ctx, agent=agent, name=_name, **kwargs)
            except (ToolDenied, ToolInvalid, ApplicationError) as exc:
                return json.dumps({"error": getattr(exc, "message", str(exc))})
            return json.dumps(result, default=str)

        tools.append(
            StructuredTool.from_function(
                func=run, name=name, description=spec.description, args_schema=spec.args_schema
            )
        )
    return tools
