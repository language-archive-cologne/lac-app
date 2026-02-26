from django.urls import path

from . import views

app_name = "dbadmin"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("stats/", views.OverviewStatsView.as_view(), name="stats"),
    path("tasks/enqueue/<slug:action>/", views.TaskEnqueueView.as_view(), name="task_enqueue"),
    path("tasks/<uuid:task_id>/status/", views.TaskStatusView.as_view(), name="task_status"),
    path("tasks/<uuid:task_id>/cancel/", views.TaskCancelView.as_view(), name="task_cancel"),
    path("tasks/history/", views.TaskHistoryView.as_view(), name="task_history"),
    path("tasks/scheduled/", views.ScheduledTasksView.as_view(), name="scheduled_tasks"),
    # Database management
    path("cleanup/", views.DatabaseCleanupView.as_view(), name="cleanup"),
    path("delete/all/", views.DatabaseDeleteAllView.as_view(), name="delete_all"),
    path("delete/all/confirm/", views.DatabaseDeleteConfirmView.as_view(), name="delete_all_confirm"),
    path("delete/collections/", views.DatabaseDeleteCollectionsView.as_view(), name="delete_collections"),
    path("delete/collections/confirm/", views.DatabaseDeleteCollectionsConfirmView.as_view(), name="delete_collections_confirm"),
    path("delete/bundles/", views.DatabaseDeleteBundlesView.as_view(), name="delete_bundles"),
    path("delete/bundles/confirm/", views.DatabaseDeleteBundlesConfirmView.as_view(), name="delete_bundles_confirm"),
]
