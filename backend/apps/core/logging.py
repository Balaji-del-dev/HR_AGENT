"""structlog setup: JSON logs carrying request_id, tenant_id and user_id.

Imported by settings, so it must not import Django models.
"""

from typing import Any

import structlog

_SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]


def configure_structlog() -> None:
    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def build_logging(*, json_output: bool, level: str) -> dict[str, Any]:
    renderer: Any = structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer(colors=False)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "foreign_pre_chain": [*_SHARED_PROCESSORS, structlog.stdlib.ExtraAdder()],
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.format_exc_info,
                    renderer,
                ],
            },
        },
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structured"}},
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            # Replace Django's own console handler so each record is written once, structured.
            "django": {"handlers": ["console"], "level": level, "propagate": False},
            "django.db.backends": {"level": "WARNING"},
            # Presidio logs one warning per unsupported-language recognizer at start-up.
            "presidio-analyzer": {"level": "ERROR"},
            "httpx": {"level": "WARNING"},
        },
    }
