"""DEV-ONLY auto-login middleware.

Logs every request in as the `superuser` account automatically when DEBUG=True,
so you never have to type a password while developing locally.

NEVER enable this in production. DEBUG must be False in production, and this
middleware is a no-op when DEBUG is False.
"""

from django.conf import settings
from django.contrib.auth import get_user_model, login


class DevAutoLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG and not request.user.is_authenticated:
            User = get_user_model()
            try:
                user = User.objects.get(username="superuser")
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            except User.DoesNotExist:
                pass
        return self.get_response(request)
