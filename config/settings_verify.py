"""Test settings that use a separate database name.

Use this when a test run must be isolated from any other test process:

    python manage.py test tests --settings=config.settings_verify
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    **DATABASES,  # noqa: F405
    "default": {
        **DATABASES["default"],  # noqa: F405
        "TEST": {
            **DATABASES["default"].get("TEST", {}),  # noqa: F405
            "NAME": "verify_payroll_audit",
        },
    },
}
