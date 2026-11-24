# payroll-audit

Automated Payroll Audit and Resource Verification System — a Django application
that records employee changes as tamper-evident audit evidence, verifies staff
identity with short video captures, routes expense claims through a
separation-of-duties approval flow, and keeps double-entry books that always
balance.

## Stack

- Python 3 / Django 6.1
- PostgreSQL
- Templates + plain CSS (no front-end build step)

## Apps

| App | Responsibility |
| --- | --- |
| `accounts` | Custom user model, roles, role-based access control |
| `employees` | Employee register, verification videos, verification email |
| `expenses` | Expense claims, approval state machine, double-entry ledger |
| `auditlog` | Append-only, hash-chained audit trail |
| `core` | Audit chain helpers, email helpers |

## Roles

`HR_OFFICER`, `APPROVER`, `AUDITOR`, `ACCOUNTANT`, `ADMIN`.

- HR officers maintain employee records but cannot approve claims.
- Approvers decide claims they did not raise; self-approval is refused.
- Auditors read the audit trail and verify the hash chain.
- The admin role cannot edit business data.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` beside `manage.py`:

```
DJANGO_SECRET_KEY=change-me
DEBUG=True

DB_NAME=payroll_audit
DB_USER=postgres
DB_PASSWORD=change-me
DB_HOST=127.0.0.1
DB_PORT=5432

AUDIT_HMAC_KEY=change-me
```

Then:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

`.env` is git-ignored and must never be committed. All data used in this
project is synthetic.

## Email (SMTP)

Email settings are read from `.env`, so delivery can be switched on without
touching code. The default backend is the console backend, which prints
messages instead of sending them.

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=your.address@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your.address@gmail.com
```

Gmail requires an app password (Google Account → Security → 2-Step
Verification → App passwords). Any other provider works too — change
`EMAIL_HOST`, `EMAIL_PORT` and the credentials.

Confirm delivery with:

```powershell
.\.venv\Scripts\python.exe manage.py send_test_email you@example.com
```

The command refuses to run while `EMAIL_HOST_USER` or `EMAIL_HOST_PASSWORD` is
blank. When email is not configured, employee verification emails are skipped
with a logged warning so record keeping never breaks.

Approvers with an email address receive the verification video for each new or
updated employee record that has a video attached.

## Dashboard

The landing page is role-aware:

- **Superuser** — a one-page money summary modelled on an audit-ready workbook:
  KPI cards for approved, debited, credited and the difference (which must read
  **0.00**), a donut chart with a colour-coded legend showing approved money by
  category, plus a dropdown that switches between breakdown **by category**,
  **by account** and **reconciliation**. Every reconciliation check must show
  **OK**; a failure is highlighted in red.
- **Other roles** — a slicer dropdown filters recent activity by entity type.
  Money totals are not exposed to non-superusers.

## Security hardening

- `config/settings_production.py` gives secure deployment defaults: `DEBUG=False`,
  `ALLOWED_HOSTS` from the environment, secure cookies, HTTPS redirect, HSTS,
  `nosniff` and `X-Frame-Options: DENY`. Run
  `python manage.py check --deploy --settings=config.settings_production` before
  deployment; a long random `DJANGO_SECRET_KEY` and explicit `ALLOWED_HOSTS`
  must be supplied in the environment.
- `accounts/backends.py` blocks an IP after five failed logins for 15 minutes.
- Verification videos must be mp4/webm/mov with a video content type and at most
  20 MB (`employees/forms.py`).
- `python manage.py export_checkpoint` writes the current chain head to
  `checkpoint/chain.json` (git-ignored). Both the dashboard and the auditor view
  verify against it, so deletion of the tail of the chain is detected. Point
  `AUDIT_CHECKPOINT_PATH` at storage outside the application host in production.

## Expense control

Claims route through approval levels defined by `ApprovalRule`: amounts up to
KES 100,000 need one approver; larger amounts need two different approvers and
move to `PENDING_L2` after the first decision. Every decision is stored as an
`ApprovalStep`, and a user cannot decide the same claim twice. Submitting a
claim raises an `Alert` for a possible duplicate or for an over-limit amount.
Alerts are resolved at `/finance/alerts/`; clearing one requires a reason and
writes an `ALERT_CLEAR` entry to the audit chain. A flag is not proof of
wrongdoing.

## Tests

```powershell
.\.venv\Scripts\python.exe manage.py test tests --noinput
```

53 tests cover the audit chain, employee services, the claim state machine,
ledger balancing, role-based views and the email flow.
