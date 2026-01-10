from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_header import BundleHeader
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo,
    BundleLocation,
)
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleStructuralInfo,
    BundleResources,
    BundleHasBundleMember,
)
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices

from .base import DaisyFormMixin


class BundleForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = Bundle
        fields = ["identifier", "import_bucket", "import_object_key"]


class BundleHeaderForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = BundleHeader
        fields = [
            "md_creator",
            "md_creation_date",
            "md_self_link",
            "md_profile",
        ]
        widgets = {
            "md_creation_date": forms.DateInput(attrs={"type": "date"}),
        }


class BundleGeneralInfoForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = BundleGeneralInfo
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


class BundleLocationForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = BundleLocation
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


class BundlePublicationInfoForm(DaisyFormMixin, forms.ModelForm):
    identifier_type = forms.ChoiceField(choices=IdentifierTypeChoices.choices)
    class Meta:
        model = BundlePublicationInfo
        fields = [
            "publication_year",
            "data_provider",
            "identifier",
            "identifier_type",
            "creators",
            "contributors",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class BundleAdministrativeInfoForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = BundleAdministrativeInfo
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


class BundleStructuralInfoForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = BundleStructuralInfo
        fields = [
            "is_member_of_collection",
            "additional_metadata_files",
            "bundle_topics",
        ]


class BundleResourcesForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = BundleResources
        fields = [
            "bundle_media_resources",
            "bundle_written_resources",
            "bundle_other_resources",
        ]


class BundleProjectsForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = Bundle
        fields = ["projects"]


class BundleMemberEntryForm(DaisyFormMixin, forms.ModelForm):
    class Meta:
        model = BundleHasBundleMember
        fields = [
            "member_uri",
            "identifier_type",
            "order",
        ]
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
