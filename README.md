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

## Tests

```powershell
.\.venv\Scripts\python.exe manage.py test tests --noinput
```

53 tests cover the audit chain, employee services, the claim state machine,
ledger balancing, role-based views and the email flow.
