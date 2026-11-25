from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("health/", views.health, name="health"),
    path("messages/", views.message_list, name="message_list"),
    path("request-access/", views.request_access, name="request_access"),
    path("access-requests/", views.access_request_list, name="access_request_list"),
    path("uat/", views.uat_start, name="uat_start"),
    path("uat/participant/", views.uat_participant, name="uat_participant"),
    path("uat/sus/<int:pk>/", views.uat_sus, name="uat_sus"),
    path("uat/results/", views.uat_results, name="uat_results"),
]
