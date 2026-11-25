"""Helpers for creating in-app messages."""

from accounts.models import AppMessage


def notify(recipient, subject, body, kind=AppMessage.INFO, sender=None):
    """Create one message for a single user."""
    if recipient is None:
        return None
    return AppMessage.objects.create(
        recipient=recipient,
        sender=sender,
        subject=subject,
        body=body,
        kind=kind,
    )


def notify_role(role_code, subject, body, kind=AppMessage.INFO, sender=None):
    """Create one message for every user holding a role."""
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.filter(roles__code=role_code).distinct()
    return [notify(user, subject, body, kind, sender) for user in users]
