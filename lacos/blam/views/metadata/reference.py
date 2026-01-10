from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from lacos.blam.forms.metadata import reference as reference_forms
from lacos.blam.models.base_project_info import ProjectInfo, FunderInfo, FunderIdentifier
from lacos.blam.models.bundle.bundle_general_info import (
    BundleKeyword,
    BundleObjectLanguage,
    BundleObjectLanguageAlternativeName,
    BundleObjectLanguageLanguageFamily,
)
from lacos.blam.models.collection.collection_general_info import (
    CollectionKeyword,
    CollectionObjectLanguage,
    CollectionObjectLanguageAlternativeName,
    CollectionObjectLanguageLanguageFamily,
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
from lacos.blam.views.metadata.base import apply_audit_fields


REFERENCE_CONFIG = {
    "collection-keywords": {
        "model": CollectionKeyword,
        "form": reference_forms.CollectionKeywordForm,
        "title": "Collection keywords",
        "fields": ["value"],
    },
    "bundle-keywords": {
        "model": BundleKeyword,
        "form": reference_forms.BundleKeywordForm,
        "title": "Bundle keywords",
        "fields": ["value"],
    },
    "collection-languages": {
        "model": CollectionObjectLanguage,
        "form": reference_forms.CollectionObjectLanguageForm,
        "title": "Collection object languages",
        "fields": ["display_name", "iso_639_3_code", "glottolog_code"],
    },
    "bundle-languages": {
        "model": BundleObjectLanguage,
        "form": reference_forms.BundleObjectLanguageForm,
        "title": "Bundle object languages",
        "fields": ["display_name", "iso_639_3_code", "glottolog_code"],
    },
    "collection-language-alt-names": {
        "model": CollectionObjectLanguageAlternativeName,
        "form": reference_forms.CollectionObjectLanguageAltNameForm,
        "title": "Collection language alternate names",
        "fields": ["value"],
    },
    "bundle-language-alt-names": {
        "model": BundleObjectLanguageAlternativeName,
        "form": reference_forms.BundleObjectLanguageAltNameForm,
        "title": "Bundle language alternate names",
        "fields": ["value"],
    },
    "collection-language-families": {
        "model": CollectionObjectLanguageLanguageFamily,
        "form": reference_forms.CollectionObjectLanguageFamilyForm,
        "title": "Collection language families",
        "fields": ["value"],
    },
    "bundle-language-families": {
        "model": BundleObjectLanguageLanguageFamily,
        "form": reference_forms.BundleObjectLanguageFamilyForm,
        "title": "Bundle language families",
        "fields": ["value"],
    },
    "collection-creators": {
        "model": CollectionCreator,
        "form": reference_forms.CollectionCreatorForm,
        "title": "Collection creators",
        "fields": ["family_name", "given_name", "name_identifier"],
    },
    "bundle-creators": {
        "model": BundleCreator,
        "form": reference_forms.BundleCreatorForm,
        "title": "Bundle creators",
        "fields": ["family_name", "given_name", "name_identifier"],
    },
    "collection-contributors": {
        "model": CollectionContributor,
        "form": reference_forms.CollectionContributorForm,
        "title": "Collection contributors",
        "fields": ["family_name", "given_name", "contributor_display_name"],
    },
    "bundle-contributors": {
        "model": BundleContributor,
        "form": reference_forms.BundleContributorForm,
        "title": "Bundle contributors",
        "fields": ["family_name", "given_name", "contributor_name"],
    },
    "bundle-contributor-names": {
        "model": BundleContributorName,
        "form": reference_forms.BundleContributorNameForm,
        "title": "Bundle contributor names",
        "fields": ["contributor_family_name", "contributor_given_name"],
    },
    "collection-licenses": {
        "model": CollectionLicense,
        "form": reference_forms.CollectionLicenseForm,
        "title": "Collection licenses",
        "fields": ["license_name", "license_identifier", "access"],
    },
    "bundle-licenses": {
        "model": BundleLicense,
        "form": reference_forms.BundleLicenseForm,
        "title": "Bundle licenses",
        "fields": ["license_name", "license_identifier", "access"],
    },
    "collection-rights-holders": {
        "model": CollectionRightsHolder,
        "form": reference_forms.CollectionRightsHolderForm,
        "title": "Collection rights holders",
        "fields": ["rights_holder_name"],
    },
    "bundle-rights-holders": {
        "model": BundleRightsHolder,
        "form": reference_forms.BundleRightsHolderForm,
        "title": "Bundle rights holders",
        "fields": ["rights_holder_name"],
    },
    "collection-rights-holder-identifiers": {
        "model": CollectionRightsHolderIdentifier,
        "form": reference_forms.CollectionRightsHolderIdentifierForm,
        "title": "Collection rights holder identifiers",
        "fields": ["identifier", "identifier_type"],
    },
    "bundle-rights-holder-identifiers": {
        "model": BundleRightsHolderIdentifier,
        "form": reference_forms.BundleRightsHolderIdentifierForm,
        "title": "Bundle rights holder identifiers",
        "fields": ["identifier", "identifier_type"],
    },
    "collection-identical-resources": {
        "model": CollectionIdenticalResource,
        "form": reference_forms.CollectionIdenticalResourceForm,
        "title": "Collection identical resources",
        "fields": ["uri"],
    },
    "bundle-identical-resources": {
        "model": BundleIdenticalResource,
        "form": reference_forms.BundleIdenticalResourceForm,
        "title": "Bundle identical resources",
        "fields": ["uri"],
    },
    "collection-additional-metadata-files": {
        "model": CollectionAdditionalMetadataFile,
        "form": reference_forms.CollectionAdditionalMetadataFileForm,
        "title": "Collection additional metadata files",
        "fields": ["file_name", "file_pid", "mime_type"],
    },
    "bundle-additional-metadata-files": {
        "model": BundleAdditionalMetadataFile,
        "form": reference_forms.BundleAdditionalMetadataFileForm,
        "title": "Bundle additional metadata files",
        "fields": ["file_name", "file_pid", "mime_type"],
    },
    "bundle-topics": {
        "model": BundleTopic,
        "form": reference_forms.BundleTopicForm,
        "title": "Bundle topics",
        "fields": ["name"],
    },
    "media-resources": {
        "model": MediaResource,
        "form": reference_forms.MediaResourceForm,
        "title": "Media resources",
        "fields": ["file_name", "file_pid", "mime_type"],
    },
    "written-resources": {
        "model": WrittenResource,
        "form": reference_forms.WrittenResourceForm,
        "title": "Written resources",
        "fields": ["file_name", "file_pid", "mime_type"],
    },
    "written-resource-annotations": {
        "model": WrittenResourceAnnotation,
        "form": reference_forms.WrittenResourceAnnotationForm,
        "title": "Written resource annotations",
        "fields": ["written_resource", "is_annotation_of"],
    },
    "other-resources": {
        "model": OtherResource,
        "form": reference_forms.OtherResourceForm,
        "title": "Other resources",
        "fields": ["file_name", "file_pid", "mime_type"],
    },
    "project-info": {
        "model": ProjectInfo,
        "form": reference_forms.ProjectInfoForm,
        "title": "Project info",
        "fields": ["project_display_name", "project_description"],
    },
    "funder-info": {
        "model": FunderInfo,
        "form": reference_forms.FunderInfoForm,
        "title": "Funder info",
        "fields": ["funder_name", "grant_identifier", "grant_uri"],
    },
    "funder-identifiers": {
        "model": FunderIdentifier,
        "form": reference_forms.FunderIdentifierForm,
        "title": "Funder identifiers",
        "fields": ["value", "identifier_type"],
    },
}


def get_reference_config(reference_slug: str) -> dict:
    config = REFERENCE_CONFIG.get(reference_slug)
    if not config:
        raise Http404("Unknown reference type")
    return config


class ReferenceListView(View):
    def get(self, request, reference_slug: str):
        config = get_reference_config(reference_slug)
        form = config["form"]()
        objects = config["model"].objects.all().order_by("pk")
        return render(
            request,
            "blam/metadata/reference_list.html",
            {
                "reference_slug": reference_slug,
                "title": config["title"],
                "form": form,
                "objects": objects,
                "fields": config["fields"],
            },
        )

    def post(self, request, reference_slug: str):
        config = get_reference_config(reference_slug)
        form = config["form"](request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            apply_audit_fields(obj, request.user)
            obj.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()
            messages.success(request, "Reference created.")
            return redirect("blam:metadata_reference_list", reference_slug=reference_slug)

        objects = config["model"].objects.all().order_by("pk")
        return render(
            request,
            "blam/metadata/reference_list.html",
            {
                "reference_slug": reference_slug,
                "title": config["title"],
                "form": form,
                "objects": objects,
                "fields": config["fields"],
            },
        )


class ReferenceEditView(View):
    def get(self, request, reference_slug: str, object_id):
        config = get_reference_config(reference_slug)
        obj = get_object_or_404(config["model"], pk=object_id)
        form = config["form"](instance=obj)
        return render(
            request,
            "blam/metadata/reference_edit.html",
            {
                "reference_slug": reference_slug,
                "title": config["title"],
                "form": form,
                "object": obj,
            },
        )

    def post(self, request, reference_slug: str, object_id):
        config = get_reference_config(reference_slug)
        obj = get_object_or_404(config["model"], pk=object_id)
        form = config["form"](request.POST, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            apply_audit_fields(obj, request.user)
            obj.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()
            messages.success(request, "Reference updated.")
            return redirect("blam:metadata_reference_list", reference_slug=reference_slug)

        return render(
            request,
            "blam/metadata/reference_edit.html",
            {
                "reference_slug": reference_slug,
                "title": config["title"],
                "form": form,
                "object": obj,
            },
        )


class ReferenceDeleteView(View):
    def post(self, request, reference_slug: str, object_id):
        config = get_reference_config(reference_slug)
        obj = get_object_or_404(config["model"], pk=object_id)
        obj.delete()
        messages.success(request, "Reference deleted.")
        return redirect("blam:metadata_reference_list", reference_slug=reference_slug)
