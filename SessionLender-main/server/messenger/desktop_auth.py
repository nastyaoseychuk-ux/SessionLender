"""Resolve opaque desktop keys only for the authenticated inbox socket."""
import re
from channels.db import database_sync_to_async
from django.conf import settings
from django.utils import timezone

from .desktop_api import token_hash
from .desktop_models import DesktopTicket


@database_sync_to_async
def find_session(ticket):
    return DesktopTicket.objects.filter(
        token_hash=token_hash(ticket),
        expires_at__gt=timezone.now(),
        session__expire_date__gt=timezone.now(),
    ).values_list('session_id', flat=True).first()


class DesktopTicketMiddleware:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        headers = list(scope.get('headers', []))
        authorization = dict(headers).get(b'authorization', b'')
        if not authorization:
            return await self.application(scope, receive, send)

        try:
            if scope.get('path') != '/ws/inbox/':
                raise ValueError('Desktop keys are inbox-only')
            scheme, ticket = authorization.decode('ascii').split(' ', 1)
            if scheme != 'Bearer' or not re.fullmatch(r'[A-Za-z0-9_-]{43}', ticket):
                raise ValueError('Invalid desktop key')
            session_key = await find_session(ticket)
            if not session_key:
                raise ValueError('Expired desktop key')
        except (ValueError, UnicodeError):
            await send({'type': 'websocket.close', 'code': 4403})
            return

        # The usual stack loads the real session and user. InboxConsumer still
        # checks expiry, password changes, membership and bans for each delivery.
        cookie = f'{settings.SESSION_COOKIE_NAME}={session_key}'.encode('ascii')
        desktop_scope = dict(scope)
        desktop_scope['headers'] = [
            (key, value) for key, value in headers
            if key.lower() not in (b'cookie', b'authorization')
        ] + [(b'cookie', cookie)]
        return await self.application(desktop_scope, receive, send)
