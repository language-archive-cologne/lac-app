from django.urls import path

from . import views

app_name = "dbadmin"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("tasks/enqueue/<slug:action>/", views.TaskEnqueueView.as_view(), name="task_enqueue"),
    path("tasks/<uuid:task_id>/status/", views.TaskStatusView.as_view(), name="task_status"),
]
