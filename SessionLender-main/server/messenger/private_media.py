import mimetypes
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from .models import Profile, Room, Post, ChatAttachment

@login_required
def media(request, name):
    if Profile.objects.filter(user=request.user, is_banned=True).exists():
        raise PermissionDenied
    field = None
    checks = [
        (Profile.objects.filter(avatar=name, is_banned=False), 'avatar'),
        (Room.objects.filter(avatar=name, members=request.user), 'avatar'),
        (Post.objects.filter(image=name, room__members=request.user), 'image'),
        (ChatAttachment.objects.filter(file=name, message__chat__memberships__user=request.user), 'file'),
    ]
    for queryset, attr in checks:
        obj = queryset.first()
        if obj is not None:
            field = getattr(obj, attr)
            break
    if not field:
        raise Http404
    try:
        response = FileResponse(field.open('rb'), content_type=mimetypes.guess_type(name)[0] or 'application/octet-stream')
    except (OSError, ValueError):
        raise Http404
    # Файли в сховищі незмінні (ім'я унікальне): чат-вкладення кешуємо на добу,
    # решту — на годину. 'private' — бо доступ залежить від учасника.
    lifetime = 86400 if name.startswith('chat/') else 3600
    response['Cache-Control'] = f'private, max-age={lifetime}'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
