"""Helpers for outbound email configuration checks and test messages."""

from django.conf import settings
from django.core.mail import send_mail

LOCAL_BACKENDS = (
    "console.EmailBackend",
    "locmem.EmailBackend",
    "filebased.EmailBackend",
    "dummy.EmailBackend",
)


def _uses_local_backend():
    return settings.EMAIL_BACKEND.endswith(LOCAL_BACKENDS)


def missing_settings():
    """Return the SMTP settings that are still blank.

    Local backends (console, locmem, file) never need credentials, so they
    always report no missing settings.
    """
    if _uses_local_backend():
        return []

    required = {
        "EMAIL_HOST": settings.EMAIL_HOST,
        "EMAIL_HOST_USER": settings.EMAIL_HOST_USER,
        "EMAIL_HOST_PASSWORD": settings.EMAIL_HOST_PASSWORD,
    }
    return [name for name, value in required.items() if not value]


def is_configured():
    """True when Django has everything it needs to deliver mail."""
    return not missing_settings()


def send_test_message(recipient):
    """Send a short message so SMTP delivery can be confirmed."""
    return send_mail(
        subject="Payroll Audit - SMTP test",
        message=(
            "This is a test message from the Automated Payroll Audit and "
            "Resource Verification System.\n\n"
            f"Backend: {settings.EMAIL_BACKEND}\n"
            f"Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}\n"
            f"From: {settings.DEFAULT_FROM_EMAIL}\n\n"
            "If you can read this, outbound email is working."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        fail_silently=False,
    )
