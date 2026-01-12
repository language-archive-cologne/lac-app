from django.urls import reverse

from lacos.blam.forms.metadata import reference as reference_forms
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo,
    BundleKeyword,
    BundleObjectLanguage,
    BundleObjectLanguageAlternativeName,
    BundleObjectLanguageLanguageFamily,
    BundleObjectLanguageTaxonomy,
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionKeyword,
    CollectionObjectLanguage,
    CollectionObjectLanguageAlternativeName,
    CollectionObjectLanguageLanguageFamily,
    CollectionObjectLanguageTaxonomy,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.views.metadata.publication_reference import (
    BasePublicationReferenceRemoveView,
    BasePublicationReferenceView,
)


COLLECTION_GENERAL_REFERENCE_CONFIG = {
    "keywords": {
        "model": CollectionKeyword,
        "form": reference_forms.CollectionKeywordForm,
        "title": "Collection keywords",
        "fields": ["value"],
        "relation": "keywords",
        "item_label": "Keyword",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "collection-keywords"},
    },
    "object-languages": {
        "model": CollectionObjectLanguage,
        "form": reference_forms.CollectionObjectLanguageForm,
        "title": "Collection object languages",
        "fields": ["display_name", "iso_639_3_code", "glottolog_code"],
        "relation": "object_languages",
        "item_label": "Object language",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "collection-languages"},
    },
}

BUNDLE_GENERAL_REFERENCE_CONFIG = {
    "keywords": {
        "model": BundleKeyword,
        "form": reference_forms.BundleKeywordForm,
        "title": "Bundle keywords",
        "fields": ["value"],
        "relation": "keywords",
        "item_label": "Keyword",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "bundle-keywords"},
    },
    "object-languages": {
        "model": BundleObjectLanguage,
        "form": reference_forms.BundleObjectLanguageForm,
        "title": "Bundle object languages",
        "fields": ["display_name", "iso_639_3_code", "glottolog_code"],
        "relation": "object_languages",
        "item_label": "Object language",
        "manage_url_name": "blam:metadata_reference_list",
        "manage_url_kwargs": {"reference_slug": "bundle-languages"},
    },
}


class CollectionGeneralReferencePanelView(BasePublicationReferenceView):
    reference_config = COLLECTION_GENERAL_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = CollectionGeneralInfo
    publication_lookup = "collection"
    parent_kwarg = "collection_id"
    panel_prefix = "collection"
    panel_url_name = "blam:collection_general_reference_panel"
    edit_url_name = "blam:collection_general_reference_edit"
    remove_url_name = "blam:collection_general_reference_remove"
    info_label = "general info"

    def get_nested_panels(self, parent, reference_slug: str, edit_object):
        if reference_slug != "object-languages":
            return []
        return [
            {
                "id": "collection-object-language-alternative-names-panel",
                "url": reverse(
                    "blam:collection_object_language_alt_names_panel",
                    kwargs={"object_language_id": edit_object.pk, "reference_slug": "alternative-names"},
                ),
                "label": "Alternative names",
            },
            {
                "id": "collection-object-language-language-families-panel",
                "url": reverse(
                    "blam:collection_object_language_families_panel",
                    kwargs={"object_language_id": edit_object.pk, "reference_slug": "language-families"},
                ),
                "label": "Language families",
            },
        ]


class CollectionGeneralReferenceEditView(CollectionGeneralReferencePanelView):
    pass


class CollectionGeneralReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = COLLECTION_GENERAL_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = CollectionGeneralInfo
    publication_lookup = "collection"
    parent_kwarg = "collection_id"
    panel_prefix = "collection"
    panel_url_name = "blam:collection_general_reference_panel"
    edit_url_name = "blam:collection_general_reference_edit"
    remove_url_name = "blam:collection_general_reference_remove"
    info_label = "general info"


class BundleGeneralReferencePanelView(BasePublicationReferenceView):
    reference_config = BUNDLE_GENERAL_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundleGeneralInfo
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle"
    panel_url_name = "blam:bundle_general_reference_panel"
    edit_url_name = "blam:bundle_general_reference_edit"
    remove_url_name = "blam:bundle_general_reference_remove"
    info_label = "general info"

    def get_nested_panels(self, parent, reference_slug: str, edit_object):
        if reference_slug != "object-languages":
            return []
        return [
            {
                "id": "bundle-object-language-alternative-names-panel",
                "url": reverse(
                    "blam:bundle_object_language_alt_names_panel",
                    kwargs={"object_language_id": edit_object.pk, "reference_slug": "alternative-names"},
                ),
                "label": "Alternative names",
            },
            {
                "id": "bundle-object-language-language-families-panel",
                "url": reverse(
                    "blam:bundle_object_language_families_panel",
                    kwargs={"object_language_id": edit_object.pk, "reference_slug": "language-families"},
                ),
                "label": "Language families",
            },
        ]


class BundleGeneralReferenceEditView(BundleGeneralReferencePanelView):
    pass


class BundleGeneralReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = BUNDLE_GENERAL_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundleGeneralInfo
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle"
    panel_url_name = "blam:bundle_general_reference_panel"
    edit_url_name = "blam:bundle_general_reference_edit"
    remove_url_name = "blam:bundle_general_reference_remove"
    info_label = "general info"


class CollectionObjectLanguageAltNamePanelView(BasePublicationReferenceView):
    reference_config = {
        "alternative-names": {
            "model": CollectionObjectLanguageAlternativeName,
            "form": reference_forms.CollectionObjectLanguageAltNameForm,
            "title": "Collection language alternative names",
            "fields": ["value"],
            "relation": "alternative_names",
            "item_label": "Alternative name",
            "manage_url_name": "blam:metadata_reference_list",
            "manage_url_kwargs": {"reference_slug": "collection-language-alt-names"},
        }
    }
    parent_model = CollectionObjectLanguage
    publication_model = CollectionObjectLanguage
    publication_lookup = "pk"
    parent_kwarg = "object_language_id"
    panel_prefix = "collection-object-language"
    panel_url_name = "blam:collection_object_language_alt_names_panel"
    edit_url_name = "blam:collection_object_language_alt_names_edit"
    remove_url_name = "blam:collection_object_language_alt_names_remove"
    use_parent_as_info = True
    info_label = "object language"


class CollectionObjectLanguageAltNameEditView(CollectionObjectLanguageAltNamePanelView):
    pass


class CollectionObjectLanguageAltNameRemoveView(BasePublicationReferenceRemoveView):
    reference_config = CollectionObjectLanguageAltNamePanelView.reference_config
    parent_model = CollectionObjectLanguage
    publication_model = CollectionObjectLanguage
    publication_lookup = "pk"
    parent_kwarg = "object_language_id"
    panel_prefix = "collection-object-language"
    panel_url_name = "blam:collection_object_language_alt_names_panel"
    edit_url_name = "blam:collection_object_language_alt_names_edit"
    remove_url_name = "blam:collection_object_language_alt_names_remove"
    use_parent_as_info = True
    info_label = "object language"


class CollectionObjectLanguageFamilyPanelView(BasePublicationReferenceView):
    reference_config = {
        "language-families": {
            "model": CollectionObjectLanguageLanguageFamily,
            "form": reference_forms.CollectionObjectLanguageFamilyForm,
            "title": "Collection language families",
            "fields": ["value"],
            "relation": "language_family",
            "item_label": "Language family",
            "manage_url_name": "blam:metadata_reference_list",
            "manage_url_kwargs": {"reference_slug": "collection-language-families"},
        }
    }
    parent_model = CollectionObjectLanguage
    publication_model = CollectionObjectLanguageTaxonomy
    publication_lookup = "object_language"
    parent_kwarg = "object_language_id"
    panel_prefix = "collection-object-language"
    panel_url_name = "blam:collection_object_language_families_panel"
    edit_url_name = "blam:collection_object_language_families_edit"
    remove_url_name = "blam:collection_object_language_families_remove"
    auto_create_info = True
    info_label = "object language taxonomy"


class CollectionObjectLanguageFamilyEditView(CollectionObjectLanguageFamilyPanelView):
    pass


class CollectionObjectLanguageFamilyRemoveView(BasePublicationReferenceRemoveView):
    reference_config = CollectionObjectLanguageFamilyPanelView.reference_config
    parent_model = CollectionObjectLanguage
    publication_model = CollectionObjectLanguageTaxonomy
    publication_lookup = "object_language"
    parent_kwarg = "object_language_id"
    panel_prefix = "collection-object-language"
    panel_url_name = "blam:collection_object_language_families_panel"
    edit_url_name = "blam:collection_object_language_families_edit"
    remove_url_name = "blam:collection_object_language_families_remove"
    auto_create_info = True
    info_label = "object language taxonomy"


class BundleObjectLanguageAltNamePanelView(BasePublicationReferenceView):
    reference_config = {
        "alternative-names": {
            "model": BundleObjectLanguageAlternativeName,
            "form": reference_forms.BundleObjectLanguageAltNameForm,
            "title": "Bundle language alternative names",
            "fields": ["value"],
            "relation": "alternative_names",
            "item_label": "Alternative name",
            "manage_url_name": "blam:metadata_reference_list",
            "manage_url_kwargs": {"reference_slug": "bundle-language-alt-names"},
        }
    }
    parent_model = BundleObjectLanguage
    publication_model = BundleObjectLanguage
    publication_lookup = "pk"
    parent_kwarg = "object_language_id"
    panel_prefix = "bundle-object-language"
    panel_url_name = "blam:bundle_object_language_alt_names_panel"
    edit_url_name = "blam:bundle_object_language_alt_names_edit"
    remove_url_name = "blam:bundle_object_language_alt_names_remove"
    use_parent_as_info = True
    info_label = "object language"


class BundleObjectLanguageAltNameEditView(BundleObjectLanguageAltNamePanelView):
    pass


class BundleObjectLanguageAltNameRemoveView(BasePublicationReferenceRemoveView):
    reference_config = BundleObjectLanguageAltNamePanelView.reference_config
    parent_model = BundleObjectLanguage
    publication_model = BundleObjectLanguage
    publication_lookup = "pk"
    parent_kwarg = "object_language_id"
    panel_prefix = "bundle-object-language"
    panel_url_name = "blam:bundle_object_language_alt_names_panel"
    edit_url_name = "blam:bundle_object_language_alt_names_edit"
    remove_url_name = "blam:bundle_object_language_alt_names_remove"
    use_parent_as_info = True
    info_label = "object language"


class BundleObjectLanguageFamilyPanelView(BasePublicationReferenceView):
    reference_config = {
        "language-families": {
            "model": BundleObjectLanguageLanguageFamily,
            "form": reference_forms.BundleObjectLanguageFamilyForm,
            "title": "Bundle language families",
            "fields": ["value"],
            "relation": "language_family",
            "item_label": "Language family",
            "manage_url_name": "blam:metadata_reference_list",
            "manage_url_kwargs": {"reference_slug": "bundle-language-families"},
        }
    }
    parent_model = BundleObjectLanguage
    publication_model = BundleObjectLanguageTaxonomy
    publication_lookup = "object_language"
    parent_kwarg = "object_language_id"
    panel_prefix = "bundle-object-language"
    panel_url_name = "blam:bundle_object_language_families_panel"
    edit_url_name = "blam:bundle_object_language_families_edit"
    remove_url_name = "blam:bundle_object_language_families_remove"
    auto_create_info = True
    info_label = "object language taxonomy"


class BundleObjectLanguageFamilyEditView(BundleObjectLanguageFamilyPanelView):
    pass


class BundleObjectLanguageFamilyRemoveView(BasePublicationReferenceRemoveView):
    reference_config = BundleObjectLanguageFamilyPanelView.reference_config
    parent_model = BundleObjectLanguage
    publication_model = BundleObjectLanguageTaxonomy
    publication_lookup = "object_language"
    parent_kwarg = "object_language_id"
    panel_prefix = "bundle-object-language"
    panel_url_name = "blam:bundle_object_language_families_panel"
    edit_url_name = "blam:bundle_object_language_families_edit"
    remove_url_name = "blam:bundle_object_language_families_remove"
    auto_create_info = True
    info_label = "object language taxonomy"
