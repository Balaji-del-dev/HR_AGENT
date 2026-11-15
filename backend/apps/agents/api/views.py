import secrets
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantAPIView, TenantViewSet
from apps.agents import selectors, services
from apps.agents.api.serializers import (
    AgentRunDetailSerializer,
    AgentRunSerializer,
    AssistantMessageIn,
    AssistantThreadSerializer,
    ResumeIn,
    RunKindIn,
)
from apps.agents.models import AgentRun, AssistantThread

UUID_PATTERN = "[0-9a-fA-F-]{36}"


def accepted(run: AgentRun) -> Response:
    return Response(AgentRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["agent-runs"])
class AgentRunViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    filterset_fields = ["kind", "status", "requisition"]
    lookup_value_regex = UUID_PATTERN

    def get_queryset(self) -> QuerySet[AgentRun]:
        if self.is_schema_request:
            return AgentRun.objects.none()
        queryset = selectors.visible_runs(self.ctx)
        if self.action == "retrieve":
            return queryset.prefetch_related("steps", "tool_calls")
        return queryset

    def get_serializer_class(self) -> type[serializers.Serializer[Any]]:
        return AgentRunDetailSerializer if self.action == "retrieve" else AgentRunSerializer

    @extend_schema(request=RunKindIn, responses={202: AgentRunSerializer})
    def create(self, request: Request) -> Response:
        payload = RunKindIn(data=request.data)
        payload.is_valid(raise_exception=True)
        return accepted(services.start(self.ctx, **payload.validated_data))

    @extend_schema(request=ResumeIn, responses={202: AgentRunSerializer})
    @action(detail=True, methods=["post"], throttle_scope="agent_runs")
    def resume(self, request: Request, pk: str) -> Response:
        payload = ResumeIn(data=request.data)
        payload.is_valid(raise_exception=True)
        return accepted(services.resume(self.ctx, run_id=UUID(pk), **payload.validated_data))

    @extend_schema(request=None, responses=AgentRunSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str) -> Response:
        return Response(AgentRunSerializer(services.cancel(self.ctx, run_id=UUID(pk))).data)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["assistant"])
class AssistantMessagesView(TenantAPIView):
    throttle_scope = "agent_runs"

    @extend_schema(request=AssistantMessageIn, responses={202: AgentRunSerializer})
    def post(self, request: Request) -> Response:
        payload = AssistantMessageIn(data=request.data)
        payload.is_valid(raise_exception=True)
        return accepted(
            services.ask_assistant(
                self.ctx, message=payload.validated_data["message"], thread_id=payload.validated_data.get("thread_id")
            )
        )


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["assistant"])
class AssistantThreadViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    serializer_class = AssistantThreadSerializer
    lookup_value_regex = UUID_PATTERN

    def get_queryset(self) -> QuerySet[AssistantThread]:
        if self.is_schema_request:
            return AssistantThread.objects.none()
        return selectors.my_threads(self.ctx)

    @extend_schema(responses=AgentRunSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def runs(self, request: Request, pk: str) -> Response:
        thread = selectors.get_my_thread(self.ctx, UUID(pk))
        return Response(AgentRunSerializer(thread.runs.order_by("created_at"), many=True).data)


WS_TICKET_PREFIX = "ws-ticket:"


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["realtime"])
class WsTicketView(TenantAPIView):
    """Browsers cannot set headers on WebSockets, so they exchange the session for a one-time ticket."""

    @extend_schema(
        request=None,
        responses={
            201: inline_serializer(
                "WsTicketOut", {"ticket": serializers.CharField(), "expires_in": serializers.IntegerField()}
            )
        },
    )
    def post(self, request: Request) -> Response:
        ticket = secrets.token_urlsafe(32)
        cache.set(
            WS_TICKET_PREFIX + ticket,
            {"user_id": str(self.ctx.user_id), "tenant_id": str(self.ctx.tenant_id)},
            timeout=settings.WS_TICKET_TTL_SECONDS,
        )
        return Response(
            {"ticket": ticket, "expires_in": settings.WS_TICKET_TTL_SECONDS}, status=status.HTTP_201_CREATED
        )


class PermissionMatrixOut(serializers.Serializer[Any]):
    roles = serializers.ListField(child=serializers.CharField())
    runs = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
    tools = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
    rules = serializers.ListField(child=serializers.DictField())


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["policies"])
class PermissionMatrixView(TenantAPIView):
    """The live policy table: which roles may start each agent and have each tool used for them."""

    @extend_schema(responses=PermissionMatrixOut)
    def get(self, request: Request) -> Response:
        from apps.accounts.roles import Role
        from policies.engine import POLICY_RULES, RUN_ROLES, TOOL_ROLES

        return Response(
            {
                "roles": list(Role.values),
                "runs": {kind: sorted(str(r) for r in roles) for kind, roles in RUN_ROLES.items()},
                "tools": {tool: sorted(str(r) for r in roles) for tool, roles in TOOL_ROLES.items()},
                "rules": POLICY_RULES,
            }
        )


class GraphNodeOut(serializers.Serializer[Any]):
    id = serializers.CharField()
    label = serializers.CharField()
    group = serializers.CharField()


class GraphEdgeOut(serializers.Serializer[Any]):
    source = serializers.CharField()
    target = serializers.CharField()
    conditional = serializers.BooleanField()


class AgentGraphOut(serializers.Serializer[Any]):
    version = serializers.CharField()
    nodes = GraphNodeOut(many=True)
    edges = GraphEdgeOut(many=True)


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["agent-runs"])
class AgentGraphView(TenantAPIView):
    """The supervisor graph's real structure (nodes and edges), for the workflow view."""

    @extend_schema(responses=AgentGraphOut)
    def get(self, request: Request) -> Response:
        from agent_engine.graphs.supervisor import AGENT_NODES, build_supervisor_graph
        from agent_engine.version import GRAPH_VERSION

        graph = build_supervisor_graph().get_graph(xray=1)
        guards = {"guard_input", "output_checks"}
        people = {"open_review", "human_review", "apply_decision"}

        def group(node_id: str) -> str:
            if node_id in ("__start__", "__end__"):
                return "terminal"
            if node_id in guards:
                return "guard"
            if node_id in people:
                return "human"
            if node_id in AGENT_NODES or node_id.startswith("candidates"):
                return "agent"
            return "control"

        return Response(
            {
                "version": GRAPH_VERSION,
                "nodes": [{"id": n, "label": n.split(":")[-1].strip("_"), "group": group(n)} for n in graph.nodes],
                "edges": [
                    {"source": e.source, "target": e.target, "conditional": bool(e.conditional)} for e in graph.edges
                ],
            }
        )
