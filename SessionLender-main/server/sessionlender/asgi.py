import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sessionlender.vercel_settings')

from django.core.asgi import get_asgi_application

django_asgi_application = get_asgi_application()

try:
    from channels.auth import AuthMiddlewareStack
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.security.websocket import AllowedHostsOriginValidator

    from messenger.routing import websocket_urlpatterns
    from messenger.desktop_auth import DesktopTicketMiddleware
except ImportError:  # pragma: no cover - keeps WSGI-style installs working
    application = django_asgi_application
else:
    application = ProtocolTypeRouter(
        {
            'http': django_asgi_application,
            'websocket': AllowedHostsOriginValidator(
                DesktopTicketMiddleware(AuthMiddlewareStack(URLRouter(websocket_urlpatterns)))
            ),
        }
    )
