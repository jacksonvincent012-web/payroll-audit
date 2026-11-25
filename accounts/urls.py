from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("uat/", views.uat_start, name="uat_start"),
    path("uat/participant/", views.uat_participant, name="uat_participant"),
    path("uat/sus/<int:pk>/", views.uat_sus, name="uat_sus"),
    path("uat/results/", views.uat_results, name="uat_results"),
]
