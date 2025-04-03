from django.urls import path

from .views.admin_views import (
    ArchivistDashboardView,
    DatabaseCleanupView,
    DatabaseDeleteAllView,
    DatabaseDeleteCollectionsView,
    DatabaseDeleteBundlesView,
    DatabaseDeleteConfirmView,
    DatabaseDeleteCollectionsConfirmView,
    DatabaseDeleteBundlesConfirmView
)

# Admin/archivist routes
urlpatterns = [
    # Dashboard
    path('dashboard/archivist/', ArchivistDashboardView.as_view(), name='blam_archivist_dashboard'),
    
    # Database operations
    path('admin/cleanup/', DatabaseCleanupView.as_view(), name='database_cleanup'),
    path('admin/delete-all/', DatabaseDeleteAllView.as_view(), name='database_delete_all'),
    path('admin/delete-all/confirm/', DatabaseDeleteConfirmView.as_view(), name='database_delete_all_confirm'),
    path('admin/delete-collections/', DatabaseDeleteCollectionsView.as_view(), name='database_delete_collections'),
    path('admin/delete-collections/confirm/', DatabaseDeleteCollectionsConfirmView.as_view(), name='database_delete_collections_confirm'),
    path('admin/delete-bundles/', DatabaseDeleteBundlesView.as_view(), name='database_delete_bundles'),
    path('admin/delete-bundles/confirm/', DatabaseDeleteBundlesConfirmView.as_view(), name='database_delete_bundles_confirm'),
] 