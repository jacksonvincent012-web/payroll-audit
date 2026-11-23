from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import render

from accounts.decorators import role_required
from expenses.models import Account, ExpenseClaim, LedgerEntry

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

    return render(
        request,
        "expenses/ledger_summary.html",
        {
            "debits": debits,
            "credits": credits,
            "difference": debits - credits,
            "by_category": by_category,
            "lines": LedgerEntry.objects.select_related("claim", "account").order_by(
                "-id"
            )[:20],
            "trial": trial,
        },
    )


@login_required
@role_required(*VIEW_ROLES, "APPROVER")
def claim_list(request):
    status = request.GET.get("status", "").strip().upper()
    claims = ExpenseClaim.objects.select_related("claimant", "decided_by").order_by("-created_at")
    if status in dict(ExpenseClaim.STATUS_CHOICES):
        claims = claims.filter(status=status)
    return render(
        request,
        "expenses/claim_list.html",
        {
            "claims": claims,
            "status": status,
            "statuses": ExpenseClaim.STATUS_CHOICES,
        },
    )


@login_required
@role_required(*VIEW_ROLES)
def account_list(request):
    accounts = Account.objects.all()
    return render(
        request,
        "expenses/account_list.html",
        {"accounts": accounts},
    )
