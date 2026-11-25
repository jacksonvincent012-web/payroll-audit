from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from django.views.decorators.http import require_http_methods

from accounts.decorators import role_required
from accounts.forms import ParticipantForm, SUSForm
from accounts.models import AppMessage, SUSResponse, UATParticipant
from auditlog.models import AuditEntry
from core.charts import chart_legend, donut_chart
from core.chain import verify
from core.checkpoint import (
    load_checkpoint,
    load_checkpoint_record,
    verify_checkpoint_signature,
)
from employees.models import Employee
from expenses.models import Account, ExpenseClaim, LedgerEntry

ZERO = Decimal("0.00")


def _money_summary():
    """Build the one-page financial summary, mirroring the Excel workbook."""
    approved = ExpenseClaim.objects.filter(status=ExpenseClaim.APPROVED)
    approved_count = approved.count()
    total_approved = approved.aggregate(total=Sum("amount"))["total"] or ZERO

    totals = LedgerEntry.objects.aggregate(
        debit=Sum("amount", filter=Q(side=LedgerEntry.DEBIT)),
        credit=Sum("amount", filter=Q(side=LedgerEntry.CREDIT)),
    )
    total_debit = totals["debit"] or ZERO
    total_credit = totals["credit"] or ZERO
    difference = total_debit - total_credit

    labels = dict(ExpenseClaim.CATEGORY_CHOICES)
    by_category = [
        {
            "name": labels.get(row["category"], row["category"]),
            "claims": row["claims"],
            "total": row["total"] or ZERO,
        }
        for row in approved.values("category")
        .annotate(claims=Count("id"), total=Sum("amount"))
        .order_by("category")
    ]

    by_account = []
    for account in Account.objects.all():
        agg = LedgerEntry.objects.filter(account=account).aggregate(
            debit=Sum("amount", filter=Q(side=LedgerEntry.DEBIT)),
            credit=Sum("amount", filter=Q(side=LedgerEntry.CREDIT)),
        )
        by_account.append(
            {
                "code": account.code,
                "name": account.name,
                "debit": agg["debit"] or ZERO,
                "credit": agg["credit"] or ZERO,
            }
        )

    posted_claims = LedgerEntry.objects.values("claim_id").distinct().count()
    checks = [
        ("Debits vs credits", difference),
        ("Approved claims vs posted claims", approved_count - posted_claims),
        ("Approved amount vs posted debits", total_approved - total_debit),
        ("Non-positive ledger lines", LedgerEntry.objects.filter(amount__lte=0).count()),
        ("Non-positive claims", ExpenseClaim.objects.filter(amount__lte=0).count()),
    ]
    reconciliation = [
        {"check": name, "value": value, "result": "OK" if value == 0 else "FAIL"}
        for name, value in checks
    ]

    def chart_for(items, title):
        total = sum((item["value"] for item in items), ZERO)
        return {
            "title": title,
            "svg": donut_chart(items, total),
            "legend": chart_legend(items, total),
        }

    charts = {
        "category": chart_for(
            [
                {"label": row["name"], "value": row["total"]}
                for row in by_category
            ],
            "Approved amount by category",
        ),
        "account": chart_for(
            [
                {"label": f"{row['code']} {row['name']}", "value": row["debit"]}
                for row in by_account
                if row["debit"] > 0
            ],
            "Debited amount by account",
        ),
        "reconciliation": chart_for(
            [
                {
                    "label": "OK",
                    "value": Decimal(sum(1 for r in reconciliation if r["result"] == "OK")),
                },
                {
                    "label": "FAIL",
                    "value": Decimal(sum(1 for r in reconciliation if r["result"] != "OK")),
                },
            ],
            "Reconciliation checks",
        ),
    }

    return {
        "approved_count": approved_count,
        "submitted_count": ExpenseClaim.objects.filter(
            status=ExpenseClaim.SUBMITTED
        ).count(),
        "total_approved": total_approved,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "difference": difference,
        "by_category": by_category,
        "by_account": by_account,
        "charts": charts,
        "reconciliation": reconciliation,
        "balanced": all(row["result"] == "OK" for row in reconciliation),
    }


def _serialise(e):
    return {
        "seq": e.seq,
        "occurred_at": e.occurred_at.isoformat(),
        "actor_id": e.actor_id,
        "action": e.action,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "old": e.old_values,
        "new": e.new_values,
        "prev_hash": e.prev_hash,
        "entry_hash": e.entry_hash,
    }


@login_required
def message_list(request):
    if request.method == "POST":
        message = get_object_or_404(
            AppMessage, pk=request.POST.get("message_id"), recipient=request.user
        )
        if message.read_at is None:
            from django.utils import timezone

            message.read_at = timezone.now()
            message.save(update_fields=["read_at"])
            messages.success(request, "Message marked as read")
        return redirect("accounts:message_list")

    inbox = request.user.app_messages.select_related("sender").all()
    return render(request, "accounts/message_list.html", {"inbox": inbox})


@require_http_methods(["GET"])
def health(request):
    """Lightweight liveness check used by monitoring and the local harness."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse(
        {
            "status": "ok",
            "users": get_user_model().objects.count(),
            "employees": Employee.objects.count(),
            "claims": ExpenseClaim.objects.count(),
            "audit_entries": AuditEntry.objects.count(),
        }
    )


@login_required
def dashboard(request):
    entries = list(AuditEntry.objects.all())
    ok, reason = verify(
        [_serialise(e) for e in entries],
        settings.AUDIT_HMAC_KEY.encode(),
        checkpoint=load_checkpoint(),
    )
    checkpoint_record = load_checkpoint_record()
    if checkpoint_record and verify_checkpoint_signature(checkpoint_record) is False:
        ok, reason = False, "checkpoint signature invalid"

    pending = ExpenseClaim.objects.filter(
        status__in=(ExpenseClaim.SUBMITTED, ExpenseClaim.PENDING_L2)
    )

    entity_choices = list(
        AuditEntry.objects.values_list("entity_type", flat=True)
        .distinct()
        .order_by("entity_type")
    )
    selected_entity = request.GET.get("entity", "")
    if selected_entity not in entity_choices:
        selected_entity = ""
    filtered = [e for e in entries if e.entity_type == selected_entity] if selected_entity else entries

    view_options = (
        ("category", "By category"),
        ("account", "By account"),
        ("reconciliation", "Reconciliation"),
    )
    view_choice = request.GET.get("view", "category")
    if view_choice not in [code for code, _ in view_options]:
        view_choice = "category"

    context = {
        "audit_count": len(entries),
        "user_count": get_user_model().objects.count(),
        "chain_ok": ok,
        "chain_reason": reason,
        "recent": filtered[-5:][::-1],
        "entity_choices": entity_choices,
        "selected_entity": selected_entity,
        "view_options": view_options,
        "view_choice": view_choice,
        "is_superuser": request.user.is_superuser,
        "recent_decisions": ExpenseClaim.objects.exclude(decided_by=None)
        .select_related("decided_by", "claimant")
        .order_by("-decided_at")[:5],
        "pending_claims": pending.select_related("claimant").order_by("-submitted_at"),
        "can_decide": request.user.is_superuser
        or request.user.roles.filter(code="APPROVER").exists(),
    }
    if request.user.is_superuser:
        money = _money_summary()
        context["money"] = money
        context["chart"] = money["charts"][view_choice]
    return render(request, "accounts/dashboard.html", context)


UAT_TASKS = {
    "HR_OFFICER": (
        "Open the employee register and find a staff number.",
        "Add an employee with a bank account and phone, then open the detail page.",
        "Confirm the audit history shows the CREATE entry.",
        "Open Verification alerts and read one flag without clearing it.",
    ),
    "APPROVER": (
        "Open All claims and find a submitted claim that is not your own.",
        "Approve a claim below KES 100,000 and confirm the ledger totals update.",
        "Try to approve your own claim and confirm the system refuses.",
        "Open Verification alerts and clear one alert with a reason.",
    ),
    "AUDITOR": (
        "Open the audit trail and verify integrity.",
        "Confirm the external checkpoint is displayed.",
        "Open an entry detail and read its hash and linked previous hash.",
        "Open an employee detail page and confirm the video and audit history.",
    ),
    "ADMIN": (
        "Open the dashboard money summary and its reconciliation checks.",
        "Switch the breakdown dropdown between category, account and reconciliation.",
        "Open the chart of accounts and confirm debits equal credits.",
    ),
}


@login_required
def uat_start(request):
    return render(request, "accounts/uat_start.html", {"tasks": UAT_TASKS})


@login_required
def uat_participant(request):
    if request.method == "POST":
        form = ParticipantForm(request.POST)
        if form.is_valid():
            participant = form.save()
            return redirect("accounts:uat_sus", pk=participant.pk)
    else:
        form = ParticipantForm()
    return render(request, "accounts/uat_participant.html", {"form": form})


@login_required
def uat_sus(request, pk):
    participant = get_object_or_404(UATParticipant, pk=pk)
    if SUSResponse.objects.filter(participant=participant).exists():
        return render(
            request,
            "accounts/uat_done.html",
            {"participant": participant, "already": True},
        )
    if request.method == "POST":
        form = SUSForm(request.POST)
        if form.is_valid():
            response = form.save(commit=False)
            response.participant = participant
            response.save()
            return render(
                request,
                "accounts/uat_done.html",
                {"participant": participant, "response": response, "already": False},
            )
    else:
        form = SUSForm()
    return render(
        request,
        "accounts/uat_sus.html",
        {"form": form, "participant": participant},
    )


@login_required
@role_required("AUDITOR", "ADMIN")
def uat_results(request):
    responses = list(
        SUSResponse.objects.select_related("participant").order_by("-completed_at")
    )
    scores = [response.score for response in responses]
    average = round(sum(scores) / len(scores), 2) if scores else None
    grouped = {}
    for response in responses:
        grouped.setdefault(response.participant.role_tested, []).append(response.score)
    by_role = {
        role: round(sum(values) / len(values), 2)
        for role, values in grouped.items()
    }
    return render(
        request,
        "accounts/uat_results.html",
        {
            "responses": responses,
            "average": average,
            "by_role": by_role,
            "benchmark": 68,
        },
    )
