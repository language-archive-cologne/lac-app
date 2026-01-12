from django.urls import reverse

from lacos.blam.forms.metadata import reference as reference_forms
from lacos.blam.models.base_project_info import FunderIdentifier, FunderInfo, ProjectInfo
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.views.metadata.publication_reference import (
    BasePublicationReferenceRemoveView,
    BasePublicationReferenceView,
)


COLLECTION_PROJECT_REFERENCE_CONFIG = {
    "projects": {
        "model": ProjectInfo,
        "form": reference_forms.ProjectInfoForm,
        "title": "Collection projects",
        "fields": ["project_display_name", "project_description"],
        "relation": "project_infos",
        "item_label": "Project",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "project-info"},
    },
}

BUNDLE_PROJECT_REFERENCE_CONFIG = {
    "projects": {
        "model": ProjectInfo,
        "form": reference_forms.ProjectInfoForm,
        "title": "Bundle projects",
        "fields": ["project_display_name", "project_description"],
        "relation": "projects",
        "item_label": "Project",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "project-info"},
    },
}


class CollectionProjectReferencePanelView(BasePublicationReferenceView):
    reference_config = COLLECTION_PROJECT_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = Collection
    publication_lookup = "pk"
    parent_kwarg = "collection_id"
    panel_prefix = "collection-projects"
    panel_url_name = "blam:collection_projects_reference_panel"
    edit_url_name = "blam:collection_projects_reference_edit"
    remove_url_name = "blam:collection_projects_reference_remove"
    info_label = "collection"
    use_parent_as_info = True

    def get_nested_panels(self, parent, reference_slug: str, edit_object):
        if reference_slug != "projects":
            return []
        return [
            {
                "id": "project-funders-panel",
                "url": reverse(
                    "blam:project_funders_panel",
                    kwargs={"project_id": edit_object.pk, "reference_slug": "funders"},
                ),
                "label": "Funders",
            }
        ]


class CollectionProjectReferenceEditView(CollectionProjectReferencePanelView):
    pass


class CollectionProjectReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = COLLECTION_PROJECT_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = Collection
    publication_lookup = "pk"
    parent_kwarg = "collection_id"
    panel_prefix = "collection-projects"
    panel_url_name = "blam:collection_projects_reference_panel"
    edit_url_name = "blam:collection_projects_reference_edit"
    remove_url_name = "blam:collection_projects_reference_remove"
    info_label = "collection"
    use_parent_as_info = True


class BundleProjectReferencePanelView(BasePublicationReferenceView):
    reference_config = BUNDLE_PROJECT_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = Bundle
    publication_lookup = "pk"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle-projects"
    panel_url_name = "blam:bundle_projects_reference_panel"
    edit_url_name = "blam:bundle_projects_reference_edit"
    remove_url_name = "blam:bundle_projects_reference_remove"
    info_label = "bundle"
    use_parent_as_info = True

    def get_nested_panels(self, parent, reference_slug: str, edit_object):
        if reference_slug != "projects":
            return []
        return [
            {
                "id": "project-funders-panel",
                "url": reverse(
                    "blam:project_funders_panel",
                    kwargs={"project_id": edit_object.pk, "reference_slug": "funders"},
                ),
                "label": "Funders",
            }
        ]


class BundleProjectReferenceEditView(BundleProjectReferencePanelView):
    pass


class BundleProjectReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = BUNDLE_PROJECT_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = Bundle
    publication_lookup = "pk"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle-projects"
    panel_url_name = "blam:bundle_projects_reference_panel"
    edit_url_name = "blam:bundle_projects_reference_edit"
    remove_url_name = "blam:bundle_projects_reference_remove"
    info_label = "bundle"
    use_parent_as_info = True


class ProjectFunderReferencePanelView(BasePublicationReferenceView):
    reference_config = {
        "funders": {
            "model": FunderInfo,
            "form": reference_forms.FunderInfoForm,
            "title": "Project funders",
            "fields": ["funder_name", "grant_identifier", "grant_uri"],
            "relation": "funder_infos",
            "item_label": "Funder",
            "manage_url_name": "blam:metadata_reference_list",
            "manage_url_kwargs": {"reference_slug": "funder-info"},
        }
    }
    parent_model = ProjectInfo
    publication_model = ProjectInfo
    publication_lookup = "pk"
    parent_kwarg = "project_id"
    panel_prefix = "project"
    panel_url_name = "blam:project_funders_panel"
    edit_url_name = "blam:project_funders_edit"
    remove_url_name = "blam:project_funders_remove"
    use_parent_as_info = True
    info_label = "project"

    def get_nested_panels(self, parent, reference_slug: str, edit_object):
        if reference_slug != "funders":
            return []
        return [
            {
                "id": "funder-identifiers-panel",
                "url": reverse(
                    "blam:funder_identifiers_panel",
                    kwargs={"funder_id": edit_object.pk, "reference_slug": "identifiers"},
                ),
                "label": "Funder identifiers",
            }
        ]


class ProjectFunderReferenceEditView(ProjectFunderReferencePanelView):
    pass


class ProjectFunderReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = ProjectFunderReferencePanelView.reference_config
    parent_model = ProjectInfo
    publication_model = ProjectInfo
    publication_lookup = "pk"
    parent_kwarg = "project_id"
    panel_prefix = "project-funders"
    panel_url_name = "blam:project_funders_panel"
    edit_url_name = "blam:project_funders_edit"
    remove_url_name = "blam:project_funders_remove"
    use_parent_as_info = True
    info_label = "project"


class FunderIdentifierPanelView(BasePublicationReferenceView):
    reference_config = {
        "identifiers": {
            "model": FunderIdentifier,
            "form": reference_forms.FunderIdentifierForm,
            "title": "Funder identifiers",
            "fields": ["value", "identifier_type"],
            "relation": "funder_identifiers",
            "item_label": "Funder identifier",
            "manage_url_name": "blam:metadata_reference_list",
            "manage_url_kwargs": {"reference_slug": "funder-identifiers"},
        }
    }
    parent_model = FunderInfo
    publication_model = FunderInfo
    publication_lookup = "pk"
    parent_kwarg = "funder_id"
    panel_prefix = "funder"
    panel_url_name = "blam:funder_identifiers_panel"
    edit_url_name = "blam:funder_identifiers_edit"
    remove_url_name = "blam:funder_identifiers_remove"
    use_parent_as_info = True
    info_label = "funder"


class FunderIdentifierEditView(FunderIdentifierPanelView):
    pass


class FunderIdentifierRemoveView(BasePublicationReferenceRemoveView):
    reference_config = FunderIdentifierPanelView.reference_config
    parent_model = FunderInfo
    publication_model = FunderInfo
    publication_lookup = "pk"
    parent_kwarg = "funder_id"
    panel_prefix = "funder-identifiers"
    panel_url_name = "blam:funder_identifiers_panel"
    edit_url_name = "blam:funder_identifiers_edit"
    remove_url_name = "blam:funder_identifiers_remove"
    use_parent_as_info = True
    info_label = "funder"
