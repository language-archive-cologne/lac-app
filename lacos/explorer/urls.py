from django.urls import path

from . import views

app_name = "explorer"

urlpatterns = [
    path(
        "collections/",
        view=views.CollectionListView.as_view(),
        name="collection_list",
    ),
    path(
        "collections/<uuid:pk>/",
        view=views.CollectionDetailView.as_view(),
        name="collection_detail",
    ),
    # Add URL pattern for bundle_detail later
]
