from .models import AuditEvent


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def log_event(action, actor=None, target='', detail='', request=None):
    return AuditEvent.objects.create(
        action=action,
        actor=actor if getattr(actor, 'pk', None) else None,
        target=str(target)[:200],
        detail=str(detail)[:500],
        ip_address=client_ip(request),
    )
