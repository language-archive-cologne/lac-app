"""Bundle retrieval and mapping helpers for OAI-PMH."""

from __future__ import annotations

from datetime import date, timezone as dt_timezone
from typing import List, MutableMapping, Mapping, Optional

from django.db.models import Prefetch, QuerySet
from django.utils import timezone

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo

from ..constants import REPO_IDENTIFIER, DEFAULT_PAGE_SIZE


GeneralInfoPrefetch = Prefetch(
    "general_info",
    queryset=BundleGeneralInfo.objects.select_related("location").prefetch_related("object_languages"),
)
PublicationInfoPrefetch = Prefetch(
    "publication_info",
    queryset=BundlePublicationInfo.objects.prefetch_related("creators"),
)
AdministrativeInfoPrefetch = Prefetch(
    "administrative_info",
    queryset=BundleAdministrativeInfo.objects.prefetch_related("licenses", "rights_holders"),
)


class BundleRecord(Mapping[str, object]):
    """Immutable mapping storing flattened bundle metadata."""

    def __init__(self, data: MutableMapping[str, object]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> object:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default=None):
        return self._data.get(key, default)


class OAIPMHBundlesResult:
    def __init__(self, identifier: str, datestamp: str, metadata: BundleRecord):
        self.identifier = identifier
        self.datestamp = datestamp
        self.metadata = metadata
        self.sets: List[str] = ["bundles"]


def fetch_bundle_records(
    *,
    offset: int,
    from_date: Optional[date] = None,
    until_date: Optional[date] = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> tuple[List[OAIPMHBundlesResult], bool]:
    qs = _base_queryset()
    if from_date is not None:
        qs = qs.filter(administrative_info__availability_date__gte=from_date)
    if until_date is not None:
        qs = qs.filter(administrative_info__availability_date__lte=until_date)

    qs = qs.distinct().order_by("identifier")

    page = list(qs[offset : offset + limit + 1])
    has_more = len(page) > limit
    if has_more:
        page = page[:limit]

    results = [
        OAIPMHBundlesResult(
            identifier=_build_oai_identifier(bundle),
            datestamp=_bundle_datestamp(bundle),
            metadata=_build_metadata(bundle),
        )
        for bundle in page
    ]
    return results, has_more


def _base_queryset() -> QuerySet[Bundle]:
    return Bundle.objects.prefetch_related(
        GeneralInfoPrefetch,
        PublicationInfoPrefetch,
        AdministrativeInfoPrefetch,
    )


def _build_oai_identifier(bundle: Bundle) -> str:
    return f"oai:{REPO_IDENTIFIER}:bundle:{bundle.identifier}"


def _bundle_datestamp(bundle: Bundle) -> str:
    updated = bundle.updated_at
    if timezone.is_naive(updated):
        updated = timezone.make_aware(updated, timezone.get_default_timezone())
    updated_utc = updated.astimezone(dt_timezone.utc)
    return updated_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_metadata(bundle: Bundle) -> BundleRecord:
    data: MutableMapping[str, object] = {}

    general = bundle.general_info.first()
    publication = bundle.publication_info.first()
    administrative = bundle.administrative_info.first()

    if general:
        data["CollectionDisplayTitle"] = general.display_title
        data["CollectionDescription"] = general.description
        data["CollectionVersion"] = general.version
        data["ObjectLanguageName"] = [lang.name for lang in general.object_languages.all()]
        data["ObjectLanguageISO639-3Code"] = [lang.iso_639_3_code for lang in general.object_languages.all()]
        location = getattr(general, "location", None)
        if location:
            data["CollectionGeoLocation"] = location.geo_location or location.location_name

    if publication:
        creators = [
            _format_person(creator.given_name, creator.family_name)
            for creator in publication.creators.all()
        ]
        data["CollectionCreator"] = [name for name in creators if name]

    if administrative:
        data["AvailabilityDate"] = administrative.availability_date.isoformat()
        data["LicenseIdentifier"] = [lic.license_identifier for lic in administrative.licenses.all()]
        data["RightsHolder"] = [holder.rights_holder_name for holder in administrative.rights_holders.all()]

    data.setdefault("CollectionCreator", [])
    data.setdefault("ObjectLanguageName", [])
    data.setdefault("ObjectLanguageISO639-3Code", [])
    data.setdefault("LicenseIdentifier", [])
    data.setdefault("RightsHolder", [])

    data["CollectionID"] = bundle.identifier

    return BundleRecord(data)


def _format_person(given: Optional[str], family: Optional[str]) -> Optional[str]:
    parts = [part for part in (given, family) if part]
    if not parts:
        return None
    return " ".join(parts)
