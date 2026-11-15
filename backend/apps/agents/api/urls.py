from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.agents.api.views import (
    AgentGraphView,
    AgentRunViewSet,
    AssistantMessagesView,
    AssistantThreadViewSet,
    PermissionMatrixView,
    WsTicketView,
)

router = SimpleRouter()
router.register("agent-runs", AgentRunViewSet, basename="agent-run")
router.register("assistant/threads", AssistantThreadViewSet, basename="assistant-thread")

urlpatterns = [
    path("assistant/messages/", AssistantMessagesView.as_view(), name="assistant-messages"),
    path("ws-tickets/", WsTicketView.as_view(), name="ws-tickets"),
    path("agent-graph/", AgentGraphView.as_view(), name="agent-graph"),
    path("policies/matrix/", PermissionMatrixView.as_view(), name="permission-matrix"),
    *router.urls,
]
