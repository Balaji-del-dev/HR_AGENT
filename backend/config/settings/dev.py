"""Local development against the machine's own Postgres and Redis.

Defaults match scripts/setup_local_db.sql, so no .env is needed.
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault("DB_USER", "hr_app")
os.environ.setdefault("DB_PASSWORD", "hr_app_dev")
os.environ.setdefault("LOG_JSON", "false")
# Agents run on the offline deterministic model unless you choose a real one:
#   LLM_PROVIDER=ollama   (local qwen2.5:1.5b; needs about 1.5 GB of free RAM)
#   LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=...   (Claude)
os.environ.setdefault("LLM_PROVIDER", "offline")
os.environ.setdefault("EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("PII_MASKER", "presidio")

from .base import *  # noqa: F403
from .base import REST_FRAMEWORK

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

CSRF_TRUSTED_ORIGINS = ["http://localhost:5180", "http://127.0.0.1:5180"]
