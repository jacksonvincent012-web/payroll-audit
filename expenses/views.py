from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.decorators import role_required
from accounts.views import _money_summary
from expenses.models import Account, Alert, ExpenseClaim, LedgerEntry
from expenses.services import ClaimError, approve_claim, clear_alert, reject_claim

VIEW_ROLES = ("ADMIN", "AUDITOR", "ACCOUNTANT")


def _total(side):
    value = LedgerEntry.objects.filter(side=side).aggregate(amount_sum=Sum("amount"))[
        "amount_sum"
    ]
    return value or Decimal("0.00")


@login_required
@role_required(*VIEW_ROLES)
def ledger_summary(request):
    debits = _total(LedgerEntry.DEBIT)
    credits = _total(LedgerEntry.CREDIT)

    rows = (
        ExpenseClaim.objects.filter(status=ExpenseClaim.APPROVED)
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    labels = dict(ExpenseClaim.CATEGORY_CHOICES)
    by_category = [
        {"label": labels.get(row["category"], row["category"]), "total": row["total"]}
        for row in rows
    ]

    trial = (
        Account.objects.filter(lines__isnull=False)
        .annotate(
            debit=Sum("lines__amount", filter=Q(lines__side=LedgerEntry.DEBIT)),
            credit=Sum("lines__amount", filter=Q(lines__side=LedgerEntry.CREDIT)),
        )
        .order_by("code")
    )

    view_options = (
        ("trial", "Trial balance by account"),
        ("category", "By category"),
        ("journal", "Recent postings"),
        ("reconciliation", "Reconciliation"),
    )
    view = request.GET.get("view", "trial")
    if view not in [code for code, _ in view_options]:
        view = "trial"

    account_code = (request.GET.get("account") or "").strip()
    account_choices = list(
        Account.objects.values_list("code", flat=True).order_by("code")
    )
    lines = LedgerEntry.objects.select_related("claim", "account").order_by("-id")
    if account_code:
        lines = lines.filter(account__code=account_code)

    posted_claims = LedgerEntry.objects.values("claim_id").distinct().count()
    checks = (
        ("Debits vs credits", debits - credits),
        (
            "Approved claims vs posted claims",
            ExpenseClaim.objects.filter(status=ExpenseClaim.APPROVED).count()
            - posted_claims,
        ),
        ("Non-positive postings", LedgerEntry.objects.filter(amount__lte=0).count()),
    )
    reconciliation = [
        {"check": name, "value": value, "result": "OK" if value == 0 else "FAIL"}
        for name, value in checks
    ]

    return render(
        request,
        "expenses/ledger_summary.html",
        {
            "debits": debits,
            "credits": credits,
            "difference": debits - credits,
            "by_category": by_category,
            "lines": lines[:50],
            "trial": trial,
            "view_options": view_options,
            "view": view,
            "account_choices": account_choices,
            "account_code": account_code,
            "reconciliation": reconciliation,
            "chart": _money_summary()["charts"]["category"],
        },
    )


@login_required
@role_required(*VIEW_ROLES, "APPROVER")
def claim_list(request):
    status = request.GET.get("status", "").strip().upper()
    query = (request.GET.get("q") or "").strip()
    claims = ExpenseClaim.objects.select_related("claimant", "decided_by").order_by("-created_at")
    if status in dict(ExpenseClaim.STATUS_CHOICES):
        claims = claims.filter(status=status)
    if query:
        claims = claims.filter(
            Q(reference__icontains=query)
            | Q(description__icontains=query)
            | Q(claimant__username__icontains=query)
            | Q(category__icontains=query)
        )
    return render(
        request,
        "expenses/claim_list.html",
        {
            "claims": claims,
            "status": status,
            "query": query,
            "statuses": ExpenseClaim.STATUS_CHOICES,
            "can_decide": request.user.is_superuser or request.user.has_role("APPROVER"),
        },
    )


@login_required
@role_required(*VIEW_ROLES, "APPROVER")
def decide_claim(request, pk):
    claim = get_object_or_404(ExpenseClaim, pk=pk)
    action = (request.POST.get("action") or "").strip().upper()
    note = (request.POST.get("note") or "").strip()
    actor = request.user
    try:
        if action == "APPROVE":
            decided = approve_claim(actor, claim, note=note)
            messages.success(request, f"{decided.reference} approved")
        elif action == "REJECT":
            decided = reject_claim(actor, claim, note=note)
            messages.success(request, f"{decided.reference} rejected")
        else:
            messages.error(request, "Unknown decision action")
            return redirect("expenses:claim_list")
    except ClaimError as exc:
        messages.error(request, str(exc))
    return redirect("expenses:claim_list")


@login_required
@role_required(*VIEW_ROLES)
def account_list(request):
    accounts = Account.objects.all()
    return render(
        request,
        "expenses/account_list.html",
        {"accounts": accounts},
    )


@login_required
@role_required("ADMIN", "AUDITOR", "APPROVER")
def alert_list(request):
    if request.method == "POST":
        alert = get_object_or_404(Alert, pk=request.POST.get("alert_id"))
        try:
            cleared = clear_alert(request.user, alert, request.POST.get("reason", ""))
            messages.success(request, f"Alert on {cleared.claim.reference} cleared")
        except ClaimError as exc:
            messages.error(request, str(exc))
        return redirect("expenses:alert_list")

    alerts = (
        Alert.objects.filter(claim__isnull=False)
        .select_related("claim", "cleared_by")
        .order_by("-raised_at")
    )
    return render(request, "expenses/alert_list.html", {"alerts": alerts})
