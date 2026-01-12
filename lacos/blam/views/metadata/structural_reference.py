from lacos.blam.forms.metadata import reference as reference_forms
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleAdditionalMetadataFile,
    BundleStructuralInfo,
    BundleTopic,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
    CollectionStructuralInfo,
)
from lacos.blam.views.metadata.publication_reference import (
    BasePublicationReferenceRemoveView,
    BasePublicationReferenceView,
)


COLLECTION_STRUCTURAL_REFERENCE_CONFIG = {
    "additional-metadata-files": {
        "model": CollectionAdditionalMetadataFile,
        "form": reference_forms.CollectionAdditionalMetadataFileForm,
        "title": "Collection additional metadata files",
        "fields": ["file_name", "file_pid", "mime_type"],
        "relation": "additional_metadata_files",
        "item_label": "Additional metadata file",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "collection-additional-metadata-files"},
    },
}

BUNDLE_STRUCTURAL_REFERENCE_CONFIG = {
    "additional-metadata-files": {
        "model": BundleAdditionalMetadataFile,
        "form": reference_forms.BundleAdditionalMetadataFileForm,
        "title": "Bundle additional metadata files",
        "fields": ["file_name", "file_pid", "mime_type"],
        "relation": "additional_metadata_files",
        "item_label": "Additional metadata file",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "bundle-additional-metadata-files"},
    },
    "bundle-topics": {
        "model": BundleTopic,
        "form": reference_forms.BundleTopicForm,
        "title": "Bundle topics",
        "fields": ["name"],
        "relation": "bundle_topics",
        "item_label": "Topic",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "bundle-topics"},
    },
}


class CollectionStructuralReferencePanelView(BasePublicationReferenceView):
    reference_config = COLLECTION_STRUCTURAL_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = CollectionStructuralInfo
    publication_lookup = "collection"
    parent_kwarg = "collection_id"
    panel_prefix = "collection-structural"
    panel_url_name = "blam:collection_structural_reference_panel"
    edit_url_name = "blam:collection_structural_reference_edit"
    remove_url_name = "blam:collection_structural_reference_remove"
    info_label = "structural info"
    auto_create_info = True


class CollectionStructuralReferenceEditView(CollectionStructuralReferencePanelView):
    pass


class CollectionStructuralReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = COLLECTION_STRUCTURAL_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = CollectionStructuralInfo
    publication_lookup = "collection"
    parent_kwarg = "collection_id"
    panel_prefix = "collection-structural"
    panel_url_name = "blam:collection_structural_reference_panel"
    edit_url_name = "blam:collection_structural_reference_edit"
    remove_url_name = "blam:collection_structural_reference_remove"
    info_label = "structural info"
    auto_create_info = True


class BundleStructuralReferencePanelView(BasePublicationReferenceView):
    reference_config = BUNDLE_STRUCTURAL_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundleStructuralInfo
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle-structural"
    panel_url_name = "blam:bundle_structural_reference_panel"
    edit_url_name = "blam:bundle_structural_reference_edit"
    remove_url_name = "blam:bundle_structural_reference_remove"
    info_label = "structural info"


class BundleStructuralReferenceEditView(BundleStructuralReferencePanelView):
    pass


class BundleStructuralReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = BUNDLE_STRUCTURAL_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundleStructuralInfo
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle-structural"
    panel_url_name = "blam:bundle_structural_reference_panel"
    edit_url_name = "blam:bundle_structural_reference_edit"
    remove_url_name = "blam:bundle_structural_reference_remove"
    info_label = "structural info"
