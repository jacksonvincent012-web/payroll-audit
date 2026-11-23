from django.urls import path

from expenses import views

app_name = "expenses"

urlpatterns = [
    path("", views.ledger_summary, name="ledger_summary"),
    path("accounts/", views.account_list, name="account_list"),
    path("claims/", views.claim_list, name="claim_list"),
    path("claims/<int:pk>/decide/", views.decide_claim, name="decide_claim"),
]
