from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
)
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo

from .base import DaisyFormMixin


class CollectionForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = Collection
        fields = ["identifier", "source_version", "import_bucket", "import_object_key"]


class CollectionHeaderForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = CollectionHeader
        fields = [
            "md_creator",
            "md_creation_date",
            "md_self_link",
            "md_profile",
            "md_collection_display_name",
        ]
        widgets = {
            "md_creation_date": forms.DateInput(attrs={"type": "date"}),
        }


class CollectionGeneralInfoForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = CollectionGeneralInfo
        fields = [
            "id_value",
            "id_type",
            "display_title",
            "description",
            "recording_date",
            "version",
            "keywords",
            "object_languages",
        ]
        widgets = {
            "recording_date": forms.DateInput(attrs={"type": "date"}),
        }


class CollectionLocationForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = CollectionLocation
        fields = [
            "geo_location",
            "location_name",
            "location_facet",
            "region_name",
            "region_facet",
            "country_name",
            "country_facet",
            "country_code",
        ]


class CollectionPublicationInfoForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = CollectionPublicationInfo
        fields = [
            "publication_year",
            "data_provider",
            "creators",
            "contributors",
        ]


class CollectionAdministrativeInfoForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = CollectionAdministrativeInfo
        fields = [
            "access_level",
            "availability_date",
            "is_derivation_of",
            "authorized_users",
            "is_identical_to",
            "licenses",
            "rights_holders",
        ]
        widgets = {
            "availability_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        access_level = cleaned_data.get("access_level")
        availability_date = cleaned_data.get("availability_date")
        authorized_users = cleaned_data.get("authorized_users")

        if access_level == "private" and not authorized_users:
            self.add_error("authorized_users", ValidationError("Authorized users are required for private access."))

        if access_level == "embargo" and availability_date:
            if availability_date <= timezone.now().date():
                self.add_error(
                    "availability_date",
                    ValidationError("Availability date must be in the future for embargoed access."),
                )

        return cleaned_data


class CollectionStructuralInfoForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = CollectionStructuralInfo
        fields = [
            "additional_metadata_files",
        ]


class CollectionProjectInfoForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = Collection
        fields = ["project_infos"]
