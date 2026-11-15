"""WebSocket routes."""

from django.urls import path

from apps.agents.consumers import NotificationsConsumer, RunEventsConsumer

websocket_urlpatterns = [
    path("ws/runs/<uuid:run_id>/", RunEventsConsumer.as_asgi()),
    path("ws/notifications/", NotificationsConsumer.as_asgi()),
]
