"""
Celery application. Queues: documents, agents, integrations, notifications
(routing lives in settings.CELERY_TASK_ROUTES).

    celery -A config worker -Q default,documents,agents,integrations,notifications
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("hr_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
# agent_engine is a plain package, not a Django app, so name its tasks module explicitly.
app.autodiscover_tasks(["agent_engine"])
