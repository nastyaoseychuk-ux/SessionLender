import hashlib

from django.conf import settings
from django.core.cache import cache


def _cache_key(identifier, prefix='login-throttle'):
    digest = hashlib.sha256(str(identifier).encode('utf-8')).hexdigest()[:32]
    return f'{prefix}:{digest}'


def is_locked(identifier):
    value = cache.get(_cache_key(identifier), 0) or 0
    return int(value) >= getattr(settings, 'LOGIN_FAILURE_LIMIT', 5)


def register_failure(identifier):
    key = _cache_key(identifier)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, getattr(settings, 'LOGIN_LOCKOUT_SECONDS', 900))
        return 1
    count = int(cache.get(key, 0) or 0)
    cache.touch(key, getattr(settings, 'LOGIN_LOCKOUT_SECONDS', 900))
    return count


def reset_failures(identifier):
    cache.delete(_cache_key(identifier))


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _throttle_key(identifier, scope):
    return _cache_key(f'{scope}:{identifier}', prefix='throttle')


def _hit(key, limit, window_seconds):
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window_seconds)
        return False
    if count == 1:
        cache.touch(key, window_seconds)
    return count > limit


def is_rate_limited_identity(identifier, scope, limit, window_seconds):
    return _hit(_throttle_key(identifier, scope), limit, window_seconds)


def is_rate_limited(request, scope, limit, window_seconds):
    ip = client_ip(request) or 'unknown'
    user_id = getattr(getattr(request, 'user', None), 'pk', None) if request is not None else None
    identifier = f'{ip}:{user_id or "anon"}'
    return is_rate_limited_identity(identifier, scope, limit, window_seconds)
