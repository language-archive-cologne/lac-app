from django.urls import reverse

from lacos.blam.forms.metadata import reference as reference_forms
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    MediaResource,
    OtherResource,
    WrittenResource,
    WrittenResourceAnnotation,
)
from lacos.blam.views.metadata.publication_reference import (
    BasePublicationReferenceRemoveView,
    BasePublicationReferenceView,
)


BUNDLE_RESOURCES_REFERENCE_CONFIG = {
    "media-resources": {
        "model": MediaResource,
        "form": reference_forms.MediaResourceForm,
        "title": "Media resources",
        "fields": ["file_name", "file_pid", "mime_type"],
        "relation": "bundle_media_resources",
        "item_label": "Media resource",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "media-resources"},
    },
    "written-resources": {
        "model": WrittenResource,
        "form": reference_forms.WrittenResourceForm,
        "title": "Written resources",
        "fields": ["file_name", "file_pid", "mime_type"],
        "relation": "bundle_written_resources",
        "item_label": "Written resource",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "written-resources"},
    },
    "other-resources": {
        "model": OtherResource,
        "form": reference_forms.OtherResourceForm,
        "title": "Other resources",
        "fields": ["file_name", "file_pid", "mime_type"],
        "relation": "bundle_other_resources",
        "item_label": "Other resource",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "other-resources"},
    },
}


class BundleResourcesReferencePanelView(BasePublicationReferenceView):
    reference_config = BUNDLE_RESOURCES_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundleResources
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle-resources"
    panel_url_name = "blam:bundle_resources_reference_panel"
    edit_url_name = "blam:bundle_resources_reference_edit"
    remove_url_name = "blam:bundle_resources_reference_remove"
    info_label = "resources info"
    auto_create_info = True

    def get_nested_panels(self, parent, reference_slug: str, edit_object):
        if reference_slug != "written-resources":
            return []
        return [
            {
                "id": "written-resource-annotations-panel",
                "url": reverse(
                    "blam:written_resource_annotations_panel",
                    kwargs={"written_resource_id": edit_object.pk, "reference_slug": "annotations"},
                ),
                "label": "Written annotations",
            }
        ]


class BundleResourcesReferenceEditView(BundleResourcesReferencePanelView):
    pass


class BundleResourcesReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = BUNDLE_RESOURCES_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundleResources
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle-resources"
    panel_url_name = "blam:bundle_resources_reference_panel"
    edit_url_name = "blam:bundle_resources_reference_edit"
    remove_url_name = "blam:bundle_resources_reference_remove"
    info_label = "resources info"
    auto_create_info = True


class WrittenResourceAnnotationPanelView(BasePublicationReferenceView):
    reference_config = {
        "annotations": {
            "model": WrittenResourceAnnotation,
            "form": reference_forms.WrittenResourceAnnotationInlineForm,
            "title": "Written resource annotations",
            "fields": ["is_annotation_of"],
            "relation": "annotations",
            "item_label": "Annotation",
            "manage_url_name": "blam:metadata_reference_list",
            "manage_url_kwargs": {"reference_slug": "written-resource-annotations"},
        }
    }
    parent_model = WrittenResource
    publication_model = WrittenResource
    publication_lookup = "pk"
    parent_kwarg = "written_resource_id"
    panel_prefix = "written-resource"
    panel_url_name = "blam:written_resource_annotations_panel"
    edit_url_name = "blam:written_resource_annotations_edit"
    remove_url_name = "blam:written_resource_annotations_remove"
    use_parent_as_info = True
    info_label = "written resource"

    def prepare_object(self, obj, publication_info):
        obj.written_resource = publication_info
        return obj


class WrittenResourceAnnotationEditView(WrittenResourceAnnotationPanelView):
    pass


class WrittenResourceAnnotationRemoveView(BasePublicationReferenceRemoveView):
    reference_config = WrittenResourceAnnotationPanelView.reference_config
    parent_model = WrittenResource
    publication_model = WrittenResource
    publication_lookup = "pk"
    parent_kwarg = "written_resource_id"
    panel_prefix = "written-resource"
    panel_url_name = "blam:written_resource_annotations_panel"
    edit_url_name = "blam:written_resource_annotations_edit"
    remove_url_name = "blam:written_resource_annotations_remove"
    use_parent_as_info = True
    info_label = "written resource"

    def remove_object(self, publication_info, relation: str, obj):
        obj.delete()
