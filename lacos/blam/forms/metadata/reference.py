from django import forms

from lacos.blam.models.base_project_info import ProjectInfo, FunderInfo, FunderIdentifier
from lacos.blam.models.bundle.bundle_general_info import (
    BundleKeyword,
    BundleObjectLanguage,
    BundleObjectLanguageAlternativeName,
    BundleObjectLanguageLanguageFamily,
    BundleObjectLanguageTaxonomy,
)
from lacos.blam.models.collection.collection_general_info import (
    CollectionKeyword,
    CollectionObjectLanguage,
    CollectionObjectLanguageAlternativeName,
    CollectionObjectLanguageLanguageFamily,
    CollectionObjectLanguageTaxonomy,
)
from lacos.blam.models.bundle.bundle_publication_info import (
    BundleCreator,
    BundleContributor,
    BundleContributorName,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionCreator,
    CollectionContributor,
)
from lacos.blam.models.bundle.bundle_administrative_info import (
    BundleLicense,
    BundleRightsHolder,
    BundleRightsHolderIdentifier,
    BundleIdenticalResource,
)
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionLicense,
    CollectionRightsHolder,
    CollectionRightsHolderIdentifier,
    CollectionIdenticalResource,
)
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleAdditionalMetadataFile,
    BundleTopic,
    MediaResource,
    WrittenResource,
    WrittenResourceAnnotation,
    OtherResource,
)
from lacos.blam.models.collection.collection_structural_info import CollectionAdditionalMetadataFile

from .base import DaisyFormMixin


def build_reference_form(model, fields, widgets=None):
    meta = type(
        "Meta",
        (),
        {
            "model": model,
            "fields": fields,
            "widgets": widgets or {},
        },
    )
    return type(
        f"{model.__name__}ReferenceForm",
        (DaisyFormMixin, forms.ModelForm),
        {"Meta": meta},
    )


CollectionKeywordForm = build_reference_form(CollectionKeyword, ["value"])
BundleKeywordForm = build_reference_form(BundleKeyword, ["value"])

CollectionObjectLanguageAltNameForm = build_reference_form(CollectionObjectLanguageAlternativeName, ["value"])
BundleObjectLanguageAltNameForm = build_reference_form(BundleObjectLanguageAlternativeName, ["value"])

CollectionObjectLanguageFamilyForm = build_reference_form(CollectionObjectLanguageLanguageFamily, ["value"])
BundleObjectLanguageFamilyForm = build_reference_form(BundleObjectLanguageLanguageFamily, ["value"])

CollectionCreatorForm = build_reference_form(
    CollectionCreator,
    ["family_name", "given_name", "name_identifier", "name_identifier_type", "affiliation"],
)
BundleCreatorForm = build_reference_form(
    BundleCreator,
    ["family_name", "given_name", "name_identifier", "name_identifier_type", "affiliation"],
)

CollectionContributorForm = build_reference_form(
    CollectionContributor,
    [
        "family_name",
        "given_name",
        "name_identifier",
        "name_identifier_type",
        "affiliation",
        "role",
        "contributor_display_name",
    ],
)
BundleContributorForm = build_reference_form(
    BundleContributor,
    [
        "family_name",
        "given_name",
        "name_identifier",
        "name_identifier_type",
        "affiliation",
        "role",
        "contributor_name",
    ],
)
BundleContributorNameForm = build_reference_form(
    BundleContributorName,
    ["contributor_family_name", "contributor_given_name"],
)

CollectionLicenseForm = build_reference_form(
    CollectionLicense,
    ["license_name", "license_identifier", "access"],
)
BundleLicenseForm = build_reference_form(
    BundleLicense,
    ["license_name", "license_identifier", "access"],
)

CollectionRightsHolderIdentifierForm = build_reference_form(
    CollectionRightsHolderIdentifier,
    ["identifier", "identifier_type"],
)
BundleRightsHolderIdentifierForm = build_reference_form(
    BundleRightsHolderIdentifier,
    ["identifier", "identifier_type"],
)

CollectionRightsHolderForm = build_reference_form(
    CollectionRightsHolder,
    ["rights_holder_name", "rights_holder_identifiers"],
)
BundleRightsHolderForm = build_reference_form(
    BundleRightsHolder,
    ["rights_holder_name", "rights_holder_identifiers"],
)

CollectionIdenticalResourceForm = build_reference_form(CollectionIdenticalResource, ["uri"])
BundleIdenticalResourceForm = build_reference_form(BundleIdenticalResource, ["uri"])

CollectionAdditionalMetadataFileForm = build_reference_form(
    CollectionAdditionalMetadataFile,
    ["file_name", "file_pid", "mime_type", "is_metadata_for", "file_description"],
)
BundleAdditionalMetadataFileForm = build_reference_form(
    BundleAdditionalMetadataFile,
    ["file_name", "file_pid", "mime_type", "is_metadata_for", "file_description"],
)

BundleTopicForm = build_reference_form(BundleTopic, ["name"])

MediaResourceForm = build_reference_form(
    MediaResource,
    ["file_name", "file_pid", "mime_type", "file_length", "file_description"],
)
WrittenResourceForm = build_reference_form(
    WrittenResource,
    ["file_name", "file_pid", "mime_type", "file_description"],
)
OtherResourceForm = build_reference_form(
    OtherResource,
    ["file_name", "file_pid", "mime_type", "file_description"],
)
WrittenResourceAnnotationForm = build_reference_form(
    WrittenResourceAnnotation,
    ["written_resource", "is_annotation_of"],
)

ProjectInfoForm = build_reference_form(
    ProjectInfo,
    ["project_display_name", "project_description", "funder_infos"],
)
FunderInfoForm = build_reference_form(
    FunderInfo,
    ["funder_name", "grant_identifier", "grant_uri", "funder_identifiers"],
)
FunderIdentifierForm = build_reference_form(
    FunderIdentifier,
    ["value", "identifier_type"],
)


class CollectionObjectLanguageForm(DaisyFormMixin, forms.ModelForm):
    language_families = forms.ModelMultipleChoiceField(
        queryset=CollectionObjectLanguageLanguageFamily.objects.all(),
        required=False,
    )

    class Meta:
        model = CollectionObjectLanguage
        fields = [
            "display_name",
            "name",
            "iso_639_3_code",
            "glottolog_code",
            "alternative_names",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        taxonomy = None
        if self.instance.pk:
            taxonomy = CollectionObjectLanguageTaxonomy.objects.filter(
                object_language=self.instance
            ).first()
        if taxonomy:
            self.fields["language_families"].initial = taxonomy.language_family.all()

    def save(self, commit=True):
        self._language_families = self.cleaned_data.get("language_families")
        return super().save(commit=commit)

    def save_m2m(self):
        super().save_m2m()
        families = getattr(self, "_language_families", None)
        if families is None:
            return
        taxonomy, _created = CollectionObjectLanguageTaxonomy.objects.get_or_create(
            object_language=self.instance
        )
        taxonomy.language_family.set(families)


class BundleObjectLanguageForm(DaisyFormMixin, forms.ModelForm):
    language_families = forms.ModelMultipleChoiceField(
        queryset=BundleObjectLanguageLanguageFamily.objects.all(),
        required=False,
    )

    class Meta:
        model = BundleObjectLanguage
        fields = [
            "display_name",
            "name",
            "iso_639_3_code",
            "glottolog_code",
            "alternative_names",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        taxonomy = None
        if self.instance.pk:
            taxonomy = BundleObjectLanguageTaxonomy.objects.filter(
                object_language=self.instance
            ).first()
        if taxonomy:
            self.fields["language_families"].initial = taxonomy.language_family.all()

    def save(self, commit=True):
        self._language_families = self.cleaned_data.get("language_families")
        return super().save(commit=commit)

    def save_m2m(self):
        super().save_m2m()
        families = getattr(self, "_language_families", None)
        if families is None:
            return
        taxonomy, _created = BundleObjectLanguageTaxonomy.objects.get_or_create(
            object_language=self.instance
        )
        taxonomy.language_family.set(families)
