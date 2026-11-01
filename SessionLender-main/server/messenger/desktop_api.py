"""Exchange the current login for an opaque, inbox-only desktop key."""
import hashlib
import secrets
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_GET

from .desktop_models import DesktopTicket

TICKET_MAX_AGE = 3600


def token_hash(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


@never_cache
@require_POST
def desktop_session(request):
    # Standard Django CSRF protection applies. Passwords and cookies stay private.
    if not request.user.is_authenticated or not request.session.session_key:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    if not request.user.is_active or request.user.profile.is_banned:
        return JsonResponse({'error': 'access_denied'}, status=403)

    ticket = secrets.token_urlsafe(32)
    DesktopTicket.objects.update_or_create(
        session_id=request.session.session_key,
        defaults={
            'token_hash': token_hash(ticket),
            'expires_at': timezone.now() + timedelta(seconds=TICKET_MAX_AGE),
        },
    )
    return JsonResponse({
        'ticket': ticket,
        'account': str(request.user.pk),
        'expires_in': TICKET_MAX_AGE,
    })


@never_cache
@require_GET
def desktop_avatar(request, user_id):
    """Read-only avatar access using the same restricted desktop key."""
    from django.contrib.auth import get_user
    from django.contrib.sessions.backends.db import SessionStore
    from .models import Profile
    from .send_api import avatar

    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer '):
        return JsonResponse({'error': 'authentication_required'}, status=401)
    ticket = authorization.removeprefix('Bearer ')
    if len(ticket) != 43 or not ticket.isascii():
        return JsonResponse({'error': 'invalid_key'}, status=403)
    session_key = DesktopTicket.objects.filter(
        token_hash=token_hash(ticket), expires_at__gt=timezone.now(),
        session__expire_date__gt=timezone.now(),
    ).values_list('session_id', flat=True).first()
    if not session_key:
        return JsonResponse({'error': 'expired_key'}, status=403)
    request.session = SessionStore(session_key=session_key)
    request.user = get_user(request)
    if not request.user.is_authenticated or not request.user.is_active or Profile.objects.filter(user=request.user, is_banned=True).exists():
        return JsonResponse({'error': 'access_denied'}, status=403)
    response = avatar(request, user_id)
    response['Cache-Control'] = 'private, no-store'
    return response
