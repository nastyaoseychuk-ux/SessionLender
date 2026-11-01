import os
import sys
from importlib.util import find_spec
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(BASE_DIR / '.env')


def env_bool(name, default='0'):
    value = os.environ.get(name, default)
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or os.environ.get('SECRET_KEY') or 'dev-only-sessionlender-change-me'
DEBUG = env_bool('DJANGO_DEBUG', os.environ.get('DEBUG', '1'))
ALLOWED_HOSTS = env_list(
    'DJANGO_ALLOWED_HOSTS',
    os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost'),
)
CSRF_TRUSTED_ORIGINS = env_list(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    os.environ.get('CSRF_TRUSTED_ORIGINS', ''),
)

INSTALLED_APPS = []

if find_spec('daphne') is not None:
    INSTALLED_APPS.append('daphne')

INSTALLED_APPS += [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

if find_spec('channels') is not None:
    INSTALLED_APPS.append('channels')

INSTALLED_APPS.append('messenger')
INSTALLED_APPS.append('friendships')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'messenger.middleware.ActiveUserMiddleware',
]

if find_spec('whitenoise') is not None:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
    # Статика роздається з ?v=… у назві — годинний кеш безпечний і зрізає
    # основну частину CDN-запитів (зараз ~76K/міс).
    WHITENOISE_MAX_AGE = 3600

ROOT_URLCONF = 'sessionlender.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'messenger.context_processors.navigation',
                'messenger.downloads.application_download',
            ],
        },
    },
]

WSGI_APPLICATION = 'sessionlender.wsgi.application'
ASGI_APPLICATION = 'sessionlender.asgi.application'

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and find_spec('dj_database_url') is not None:
    import dj_database_url

    DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.environ.get('SQLITE_NAME', 'db.sqlite3'),
        }
    }

REDIS_URL = os.environ.get('REDIS_URL', '').strip()

if REDIS_URL and find_spec('django_redis') is not None:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'sessionlender',
        }
    }

if REDIS_URL and find_spec('channels_redis') is not None:
    # Upstash-проксі закриває неактивні з'єднання — без keepalive/retry pubsub-читання
    # у channels-redis періодично валиться «Timeout reading from …:6379» і обриває WS.
    channel_layer_url = REDIS_URL + (
        ('&' if '?' in REDIS_URL else '?')
        + 'socket_keepalive=true&health_check_interval=30&retry_on_timeout=true'
    )
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [channel_layer_url]},
        }
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'uk'
TIME_ZONE = 'Europe/Kyiv'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
PRIVATE_MEDIA_ROOT = BASE_DIR / 'private_media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Upload limits shared by forms; Vercel overrides them below its 4.5 MB body cap.
MAX_POST_IMAGE_BYTES = int(os.environ.get('MAX_POST_IMAGE_BYTES', 5 * 1024 * 1024))
MAX_CHAT_FILE_BYTES = int(os.environ.get('MAX_CHAT_FILE_BYTES', 10 * 1024 * 1024))
MAX_CHAT_TOTAL_BYTES = int(os.environ.get('MAX_CHAT_TOTAL_BYTES', 25 * 1024 * 1024))

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# Test builds served from the top bar; override with environment variables.
ANDROID_DOWNLOAD_URL = os.environ.get(
    'ANDROID_DOWNLOAD_URL',
    'https://drive.google.com/file/d/1xJwMOrZ2CPHLRP14Xy4NMz6t2-YDPMQB/view?usp=sharing',
)
DESKTOP_DOWNLOAD_URL = os.environ.get(
    'DESKTOP_DOWNLOAD_URL',
    'https://drive.google.com/file/d/11aBK78bDHhTh3FXC6jAJA3rrKi0mKXI_/view?usp=sharing',
)

# Brute-force protection for the password login form.
LOGIN_FAILURE_LIMIT = int(os.environ.get('LOGIN_FAILURE_LIMIT', '5'))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get('LOGIN_LOCKOUT_SECONDS', '900'))
TEST = len(sys.argv) > 1 and sys.argv[1] == 'test'

# Rate limiting for actions
MESSAGE_RATE_LIMIT = int(os.environ.get('MESSAGE_RATE_LIMIT', '30'))
MESSAGE_RATE_WINDOW = int(os.environ.get('MESSAGE_RATE_WINDOW', '60'))
COMMENT_RATE_LIMIT = int(os.environ.get('COMMENT_RATE_LIMIT', '20'))
COMMENT_RATE_WINDOW = int(os.environ.get('COMMENT_RATE_WINDOW', '60'))
ROOM_CREATE_RATE_LIMIT = int(os.environ.get('ROOM_CREATE_RATE_LIMIT', '5'))
ROOM_CREATE_RATE_WINDOW = int(os.environ.get('ROOM_CREATE_RATE_WINDOW', '3600'))
UPLOAD_RATE_LIMIT = int(os.environ.get('UPLOAD_RATE_LIMIT', '10'))
UPLOAD_RATE_WINDOW = int(os.environ.get('UPLOAD_RATE_WINDOW', '60'))

SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', os.environ.get('SECURE_SSL_REDIRECT', '1'))
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    if find_spec('whitenoise') is not None:
        STORAGES = {
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {
                'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
            },
        }

SENTRY_DSN = os.environ.get('SENTRY_DSN') or os.environ.get('DJANGO_SENTRY_DSN')
if SENTRY_DSN and find_spec('sentry_sdk') is not None:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.0')),
        send_default_pii=False,
    )

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'messenger.logging_config.JsonFormatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'messenger': {
            'handlers': ['console'],
            'level': os.environ.get('LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}
