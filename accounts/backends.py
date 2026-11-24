"""Authentication backend with a small, per-IP failed-login limiter.

The counter lives in Django's cache (locmem in development; use Redis or
Memcached in production so the limit is shared across application servers).
"""

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.core.cache import cache


def _client_ip(request):
    if request is None:
        return "unknown"
    return request.META.get("REMOTE_ADDR", "unknown")


def _cache_key(ip):
    return f"login-fails:{ip}"


class RateLimitedBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        ip = _client_ip(request)
        key = _cache_key(ip)
        limit = getattr(settings, "LOGIN_FAIL_LIMIT", 5)

        if cache.get(key, 0) >= limit:
            return None

        user = super().authenticate(
            request, username=username, password=password, **kwargs
        )
        if user is None:
            failures = cache.get(key, 0) + 1
            cache.set(key, failures, getattr(settings, "LOGIN_FAIL_WINDOW", 900))
        elif user is not None:
            cache.delete(key)
        return user
