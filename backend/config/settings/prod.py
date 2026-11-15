"""Production and staging. Every secret comes from the environment (Vault / Secrets Manager)."""

from config.env import env_bool, env_int, env_list, env_str

from .base import *  # noqa: F403

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# System mail (password resets, admin alerts). Candidate email goes through the
# communications app, only from approved drafts.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env_str("SMTP_HOST"),
            "port": env_int("SMTP_PORT", 587),
            "username": env_str("SMTP_USERNAME", ""),
            "password": env_str("SMTP_PASSWORD", ""),
            "use_tls": env_bool("SMTP_USE_TLS", default=True),
        },
    },
}
