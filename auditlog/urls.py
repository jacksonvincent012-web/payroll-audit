from django.urls import path

from auditlog import views

app_name = "auditlog"

urlpatterns = [
    path("", views.entry_list, name="entry_list"),
]
