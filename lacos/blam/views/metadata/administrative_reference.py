from django.urls import reverse

from lacos.blam.forms.metadata import reference as reference_forms
from lacos.blam.models.bundle.bundle_administrative_info import (
    BundleAdministrativeInfo,
    BundleIdenticalResource,
    BundleLicense,
    BundleRightsHolder,
    BundleRightsHolderIdentifier,
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionIdenticalResource,
    CollectionLicense,
    CollectionRightsHolder,
    CollectionRightsHolderIdentifier,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.views.metadata.publication_reference import (
    BasePublicationReferenceRemoveView,
    BasePublicationReferenceView,
)


COLLECTION_ADMIN_REFERENCE_CONFIG = {
    "licenses": {
        "model": CollectionLicense,
        "form": reference_forms.CollectionLicenseForm,
        "title": "Collection licenses",
        "fields": ["license_name", "license_identifier", "access"],
        "relation": "licenses",
        "item_label": "License",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "collection-licenses"},
    },
    "rights-holders": {
        "model": CollectionRightsHolder,
        "form": reference_forms.CollectionRightsHolderForm,
        "title": "Collection rights holders",
        "fields": ["rights_holder_name"],
        "relation": "rights_holders",
        "item_label": "Rights holder",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "collection-rights-holders"},
    },
    "identical-resources": {
        "model": CollectionIdenticalResource,
        "form": reference_forms.CollectionIdenticalResourceForm,
        "title": "Collection identical resources",
        "fields": ["uri"],
        "relation": "is_identical_to",
        "item_label": "Identical resource",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "collection-identical-resources"},
    },
}

BUNDLE_ADMIN_REFERENCE_CONFIG = {
    "licenses": {
        "model": BundleLicense,
        "form": reference_forms.BundleLicenseForm,
        "title": "Bundle licenses",
        "fields": ["license_name", "license_identifier", "access"],
        "relation": "licenses",
        "item_label": "License",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "bundle-licenses"},
    },
    "rights-holders": {
        "model": BundleRightsHolder,
        "form": reference_forms.BundleRightsHolderForm,
        "title": "Bundle rights holders",
        "fields": ["rights_holder_name"],
        "relation": "rights_holders",
        "item_label": "Rights holder",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "bundle-rights-holders"},
    },
    "identical-resources": {
        "model": BundleIdenticalResource,
        "form": reference_forms.BundleIdenticalResourceForm,
        "title": "Bundle identical resources",
        "fields": ["uri"],
        "relation": "is_identical_to",
        "item_label": "Identical resource",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "bundle-identical-resources"},
    },
}


class CollectionAdministrativeReferencePanelView(BasePublicationReferenceView):
    reference_config = COLLECTION_ADMIN_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = CollectionAdministrativeInfo
    publication_lookup = "collection"
    parent_kwarg = "collection_id"
    panel_prefix = "collection-admin"
    panel_url_name = "blam:collection_administrative_reference_panel"
    edit_url_name = "blam:collection_administrative_reference_edit"
    remove_url_name = "blam:collection_administrative_reference_remove"
    info_label = "administrative info"

    def get_nested_panels(self, parent, reference_slug: str, edit_object):
        if reference_slug != "rights-holders":
            return []
        return [
            {
                "id": "collection-rights-holder-identifiers-panel",
                "url": reverse(
                    "blam:collection_rights_holder_identifiers_panel",
                    kwargs={"rights_holder_id": edit_object.pk, "reference_slug": "identifiers"},
                ),
                "label": "Rights holder identifiers",
            }
        ]


class CollectionAdministrativeReferenceEditView(CollectionAdministrativeReferencePanelView):
    pass


class CollectionAdministrativeReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = COLLECTION_ADMIN_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = CollectionAdministrativeInfo
    publication_lookup = "collection"
    parent_kwarg = "collection_id"
    panel_prefix = "collection-admin"
    panel_url_name = "blam:collection_administrative_reference_panel"
    edit_url_name = "blam:collection_administrative_reference_edit"
    remove_url_name = "blam:collection_administrative_reference_remove"
    info_label = "administrative info"


class BundleAdministrativeReferencePanelView(BasePublicationReferenceView):
    reference_config = BUNDLE_ADMIN_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundleAdministrativeInfo
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle-admin"
    panel_url_name = "blam:bundle_administrative_reference_panel"
    edit_url_name = "blam:bundle_administrative_reference_edit"
    remove_url_name = "blam:bundle_administrative_reference_remove"
    info_label = "administrative info"

    def get_nested_panels(self, parent, reference_slug: str, edit_object):
        if reference_slug != "rights-holders":
            return []
        return [
            {
                "id": "bundle-rights-holder-identifiers-panel",
                "url": reverse(
                    "blam:bundle_rights_holder_identifiers_panel",
                    kwargs={"rights_holder_id": edit_object.pk, "reference_slug": "identifiers"},
                ),
                "label": "Rights holder identifiers",
            }
        ]


class BundleAdministrativeReferenceEditView(BundleAdministrativeReferencePanelView):
    pass


class BundleAdministrativeReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = BUNDLE_ADMIN_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundleAdministrativeInfo
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle-admin"
    panel_url_name = "blam:bundle_administrative_reference_panel"
    edit_url_name = "blam:bundle_administrative_reference_edit"
    remove_url_name = "blam:bundle_administrative_reference_remove"
    info_label = "administrative info"


class CollectionRightsHolderIdentifierPanelView(BasePublicationReferenceView):
    reference_config = {
        "identifiers": {
            "model": CollectionRightsHolderIdentifier,
            "form": reference_forms.CollectionRightsHolderIdentifierForm,
            "title": "Collection rights holder identifiers",
            "fields": ["identifier", "identifier_type"],
            "relation": "rights_holder_identifiers",
            "item_label": "Rights holder identifier",
            "manage_url_name": "blam:metadata_reference_list",
            "manage_url_kwargs": {"reference_slug": "collection-rights-holder-identifiers"},
        }
    }
    parent_model = CollectionRightsHolder
    publication_model = CollectionRightsHolder
    publication_lookup = "pk"
    parent_kwarg = "rights_holder_id"
    panel_prefix = "collection-rights-holder"
    panel_url_name = "blam:collection_rights_holder_identifiers_panel"
    edit_url_name = "blam:collection_rights_holder_identifiers_edit"
    remove_url_name = "blam:collection_rights_holder_identifiers_remove"
    use_parent_as_info = True
    info_label = "rights holder"


class CollectionRightsHolderIdentifierEditView(CollectionRightsHolderIdentifierPanelView):
    pass


class CollectionRightsHolderIdentifierRemoveView(BasePublicationReferenceRemoveView):
    reference_config = CollectionRightsHolderIdentifierPanelView.reference_config
    parent_model = CollectionRightsHolder
    publication_model = CollectionRightsHolder
    publication_lookup = "pk"
    parent_kwarg = "rights_holder_id"
    panel_prefix = "collection-rights-holder"
    panel_url_name = "blam:collection_rights_holder_identifiers_panel"
    edit_url_name = "blam:collection_rights_holder_identifiers_edit"
    remove_url_name = "blam:collection_rights_holder_identifiers_remove"
    use_parent_as_info = True
    info_label = "rights holder"


class BundleRightsHolderIdentifierPanelView(BasePublicationReferenceView):
    reference_config = {
        "identifiers": {
            "model": BundleRightsHolderIdentifier,
            "form": reference_forms.BundleRightsHolderIdentifierForm,
            "title": "Bundle rights holder identifiers",
            "fields": ["identifier", "identifier_type"],
            "relation": "rights_holder_identifiers",
            "item_label": "Rights holder identifier",
            "manage_url_name": "blam:metadata_reference_list",
            "manage_url_kwargs": {"reference_slug": "bundle-rights-holder-identifiers"},
        }
    }
    parent_model = BundleRightsHolder
    publication_model = BundleRightsHolder
    publication_lookup = "pk"
    parent_kwarg = "rights_holder_id"
    panel_prefix = "bundle-rights-holder"
    panel_url_name = "blam:bundle_rights_holder_identifiers_panel"
    edit_url_name = "blam:bundle_rights_holder_identifiers_edit"
    remove_url_name = "blam:bundle_rights_holder_identifiers_remove"
    use_parent_as_info = True
    info_label = "rights holder"


class BundleRightsHolderIdentifierEditView(BundleRightsHolderIdentifierPanelView):
    pass


class BundleRightsHolderIdentifierRemoveView(BasePublicationReferenceRemoveView):
    reference_config = BundleRightsHolderIdentifierPanelView.reference_config
    parent_model = BundleRightsHolder
    publication_model = BundleRightsHolder
    publication_lookup = "pk"
    parent_kwarg = "rights_holder_id"
    panel_prefix = "bundle-rights-holder"
    panel_url_name = "blam:bundle_rights_holder_identifiers_panel"
    edit_url_name = "blam:bundle_rights_holder_identifiers_edit"
    remove_url_name = "blam:bundle_rights_holder_identifiers_remove"
    use_parent_as_info = True
    info_label = "rights holder"
