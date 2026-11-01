"""Vercel: persistent PostgreSQL, shared Redis channels, Blob media. No disk writes."""

from .settings import *
from django.core.exceptions import ImproperlyConfigured
import dj_database_url

LOCAL = os.environ.get("LOCAL_DEVELOPMENT") == "1" and os.environ.get("VERCEL") != "1"
DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY == "dev-only-sessionlender-change-me":
    raise ImproperlyConfigured(
        "Set a persistent DJANGO_SECRET_KEY in Vercel Environment Variables."
    )

hosts = [
    v.strip()
    for v in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if v.strip()
]
for name in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
    if os.environ.get(name):
        hosts.append(os.environ[name].removeprefix("https://").rstrip("/"))
if LOCAL:
    hosts += ["localhost", "127.0.0.1", "testserver"]
if not hosts:
    raise ImproperlyConfigured(
        "Set DJANGO_ALLOWED_HOSTS or use Vercel system domain variables."
    )
ALLOWED_HOSTS = list(set(hosts))
CSRF_TRUSTED_ORIGINS = ["https://" + h for h in ALLOWED_HOSTS if not h.startswith(".")]
CSRF_TRUSTED_ORIGINS += [
    v.strip()
    for v in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if v.strip()
]

url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
if url:
    if not url.startswith(("postgres://", "postgresql://")):
        raise ImproperlyConfigured("DATABASE_URL must be a PostgreSQL connection URL.")
    DATABASES = {
        "default": dj_database_url.parse(url, conn_max_age=0, ssl_require=not LOCAL)
    }
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
elif LOCAL:
    DATABASES["default"]["NAME"] = os.environ.get(
        "SQLITE_PATH", str(BASE_DIR / "db.sqlite3")
    )
else:
    raise ImproperlyConfigured(
        "Connect PostgreSQL (for example Neon) and set DATABASE_URL. SQLite is not persistent on Vercel."
    )

redis = os.environ.get("REDIS_URL")
if redis:
    if not redis.startswith(("redis://", "rediss://")):
        raise ImproperlyConfigured(
            "REDIS_URL must use redis:// or rediss://, not an HTTPS REST endpoint."
        )
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                # Див. settings.py: keepalive/retry проти «Timeout reading» від Upstash.
                "hosts": [
                    redis
                    + (
                        ("&" if "?" in redis else "?")
                        + "socket_keepalive=true&health_check_interval=30&retry_on_timeout=true"
                    )
                ],
                "prefix": os.environ.get(
                    "REDIS_PREFIX",
                    "sessionlender-" + os.environ.get("VERCEL_ENV", "local"),
                ),
                "group_expiry": 600,
                "capacity": 200,
            },
        }
    }
elif LOCAL:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
else:
    raise ImproperlyConfigured(
        "Connect Redis and set its TCP/TLS REDIS_URL for cross-instance WebSockets."
    )

if os.environ.get("BLOB_READ_WRITE_TOKEN"):
    STORAGES = {
        "default": {"BACKEND": "messenger.blob_storage.VercelBlobStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
elif not LOCAL:
    raise ImproperlyConfigured(
        "Connect a public Vercel Blob store and set BLOB_READ_WRITE_TOKEN."
    )

ROOT_URLCONF = "sessionlender.vercel_urls"
ASGI_APPLICATION = "sessionlender.vercel_asgi.application"
SESSION_COOKIE_SECURE = not LOCAL
CSRF_COOKIE_SECURE = not LOCAL
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if not LOCAL else None
FILE_UPLOAD_TEMP_DIR = "/tmp" if os.environ.get("VERCEL") == "1" else None
# Vercel Functions reject request bodies >4.5 MB. Keep uploads below it.
MAX_POST_IMAGE_BYTES = 4 * 1024 * 1024
MAX_CHAT_FILE_BYTES = 4 * 1024 * 1024
MAX_CHAT_TOTAL_BYTES = 4 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 4_450_000
FILE_UPLOAD_MAX_MEMORY_SIZE = 4_450_000

SENTRY_DSN = os.environ.get("SENTRY_DSN") or os.environ.get("DJANGO_SENTRY_DSN")
if SENTRY_DSN and find_spec("sentry_sdk") is not None:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,
    )
