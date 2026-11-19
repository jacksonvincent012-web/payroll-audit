from functools import wraps

from django.core.exceptions import PermissionDenied


def role_required(*codes):
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser:
                return view(request, *args, **kwargs)
            if user.roles.filter(code__in=codes).exists():
                return view(request, *args, **kwargs)
            raise PermissionDenied

        return _wrapped

    return decorator
