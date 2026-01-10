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
from .views.crud import delete_blam_model
from .views.metadata import (
    CollectionListView,
    CollectionCreateView,
    CollectionOverviewView,
    CollectionHeaderView,
    CollectionGeneralInfoView,
    CollectionPublicationInfoView,
    CollectionAdministrativeInfoView,
    CollectionStructuralInfoView,
    CollectionProjectInfoView,
    BundleListView,
    BundleCreateView,
    BundleOverviewView,
    BundleHeaderView,
    BundleGeneralInfoView,
    BundlePublicationInfoView,
    BundleAdministrativeInfoView,
    BundleStructuralInfoView,
    BundleMembersView,
    BundleResourcesView,
    BundleProjectsView,
    ReferenceListView,
    ReferenceEditView,
    ReferenceDeleteView,
)

app_name = "blam"

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
    
    # API endpoints for file browser integration
    path('delete-model/<str:model_type>/<uuid:object_id>/', delete_blam_model, name='delete_model'),

    # Metadata CRUD
    path('metadata/collections/', CollectionListView.as_view(), name='collection_metadata_list'),
    path('metadata/collections/new/', CollectionCreateView.as_view(), name='collection_metadata_create'),
    path('metadata/collections/<uuid:collection_id>/', CollectionOverviewView.as_view(), name='collection_metadata_overview'),
    path('metadata/collections/<uuid:collection_id>/header/', CollectionHeaderView.as_view(), name='collection_metadata_header'),
    path('metadata/collections/<uuid:collection_id>/general/', CollectionGeneralInfoView.as_view(), name='collection_metadata_general'),
    path('metadata/collections/<uuid:collection_id>/publication/', CollectionPublicationInfoView.as_view(), name='collection_metadata_publication'),
    path('metadata/collections/<uuid:collection_id>/administrative/', CollectionAdministrativeInfoView.as_view(), name='collection_metadata_administrative'),
    path('metadata/collections/<uuid:collection_id>/structural/', CollectionStructuralInfoView.as_view(), name='collection_metadata_structural'),
    path('metadata/collections/<uuid:collection_id>/projects/', CollectionProjectInfoView.as_view(), name='collection_metadata_projects'),

    path('metadata/bundles/', BundleListView.as_view(), name='bundle_metadata_list'),
    path('metadata/bundles/new/', BundleCreateView.as_view(), name='bundle_metadata_create'),
    path('metadata/bundles/<uuid:bundle_id>/', BundleOverviewView.as_view(), name='bundle_metadata_overview'),
    path('metadata/bundles/<uuid:bundle_id>/header/', BundleHeaderView.as_view(), name='bundle_metadata_header'),
    path('metadata/bundles/<uuid:bundle_id>/general/', BundleGeneralInfoView.as_view(), name='bundle_metadata_general'),
    path('metadata/bundles/<uuid:bundle_id>/publication/', BundlePublicationInfoView.as_view(), name='bundle_metadata_publication'),
    path('metadata/bundles/<uuid:bundle_id>/administrative/', BundleAdministrativeInfoView.as_view(), name='bundle_metadata_administrative'),
    path('metadata/bundles/<uuid:bundle_id>/structural/', BundleStructuralInfoView.as_view(), name='bundle_metadata_structural'),
    path('metadata/bundles/<uuid:bundle_id>/members/', BundleMembersView.as_view(), name='bundle_metadata_members'),
    path('metadata/bundles/<uuid:bundle_id>/resources/', BundleResourcesView.as_view(), name='bundle_metadata_resources'),
    path('metadata/bundles/<uuid:bundle_id>/projects/', BundleProjectsView.as_view(), name='bundle_metadata_projects'),

    path('metadata/reference/<slug:reference_slug>/', ReferenceListView.as_view(), name='metadata_reference_list'),
    path('metadata/reference/<slug:reference_slug>/<str:object_id>/', ReferenceEditView.as_view(), name='metadata_reference_edit'),
    path('metadata/reference/<slug:reference_slug>/<str:object_id>/delete/', ReferenceDeleteView.as_view(), name='metadata_reference_delete'),
]
