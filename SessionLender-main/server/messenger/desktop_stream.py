"""Server-pushed fallback when a hosting proxy cannot upgrade WebSockets."""
import asyncio
import json
import re
import time

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth import get_user
from django.contrib.sessions.backends.db import SessionStore
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone

from .desktop_api import token_hash
from .desktop_models import DesktopTicket
from .models import Profile
from .realtime import InboxConsumer


@database_sync_to_async
def authorized_scope(request):
    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer '):
        return None
    ticket = authorization.removeprefix('Bearer ')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', ticket):
        return None
    key = DesktopTicket.objects.filter(
        token_hash=token_hash(ticket), expires_at__gt=timezone.now(),
        session__expire_date__gt=timezone.now(),
    ).values_list('session_id', flat=True).first()
    if not key:
        return None
    session = SessionStore(session_key=key)
    request.session = session
    user = get_user(request)
    if not user.is_authenticated or not user.is_active:
        return None
    if Profile.objects.filter(user=user, is_banned=True).exists():
        return None
    return {'user': user, 'session': session}


def encode_event(payload):
    return 'data: ' + json.dumps(payload, ensure_ascii=False) + '\n\n'


async def event_stream(scope, layer):
    group = f'user_{scope["user"].pk}'
    channel = await layer.new_channel('desktop.stream.')
    await layer.group_add(group, channel)
    consumer = InboxConsumer()
    consumer.scope = scope
    try:
        yield encode_event({'type': 'ready'})
        for message_id in await consumer.missed_messages():
            notice = await consumer.notification({'kind': 'message', 'id': message_id})
            if notice:
                yield encode_event(notice)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                event = await asyncio.wait_for(layer.receive(channel), timeout=20)
            except asyncio.TimeoutError:
                yield ': keepalive\n\n'
                continue
            if event.get('type') == 'server.notice':
                notice = await consumer.notification(event)
                if notice:
                    yield encode_event(notice)
    finally:
        await layer.group_discard(group, channel)


async def desktop_events(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'method_not_allowed'}, status=405)
    scope = await authorized_scope(request)
    if scope is None:
        return JsonResponse({'error': 'invalid_session'}, status=403)
    layer = get_channel_layer()
    if layer is None:
        return JsonResponse({'error': 'relay_unavailable'}, status=503)
    response = StreamingHttpResponse(event_stream(scope, layer), content_type='text/event-stream')
    response['Cache-Control'] = 'private, no-store'
    response['X-Accel-Buffering'] = 'no'
    response['Vary'] = 'Authorization'
    return response
