from django.urls import path

from employees import views

app_name = "employees"

urlpatterns = [
    path("", views.employee_list, name="employee_list"),
    path("new/", views.employee_create, name="employee_create"),
    path("<int:pk>/edit/", views.employee_edit, name="employee_edit"),
    path("autosave/", views.employee_autosave, name="employee_autosave"),
]