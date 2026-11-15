"""
Test settings.

The suite connects as the owner role, because creating the test database and
running migrations needs it. Each DB test then switches to the runtime role
with `SET ROLE` (see conftest.py), so Row-Level Security applies exactly as in
production.
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-insecure-key")
os.environ.setdefault("DB_USER", "hr_owner")
os.environ.setdefault("DB_PASSWORD", "hr_owner_dev")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from .base import *  # noqa: F403

DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Agents run against scripted models and an in-memory checkpointer; no network.
LLM_PROVIDER = "fake"
LLM_MODEL = "scripted"
LLM_FALLBACK_PROVIDER = ""
EMBEDDING_PROVIDER = "hash"
PII_MASKER = "patterns"
AGENT_CHECKPOINTER = "memory"
VECTOR_BACKEND = "python"
OBJECT_STORAGE_ROOT = Path(tempfile.mkdtemp(prefix="hr-objects-"))

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = dict.fromkeys(  # noqa: F405
    ("user", "anon", "agent_runs", "login", "webhooks"), "10000/min"
)
