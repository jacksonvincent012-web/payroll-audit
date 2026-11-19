from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("audit/", include("auditlog.urls")),
    path("", include("accounts.urls")),
]
