"""BLAM metadata serializer for OAI-PMH."""

from __future__ import annotations

from typing import Mapping

from lacos.blam.mappers.collection.write import CollectionExporter
from lacos.blam.mappers.bundle.write import BundleExporter
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle

BLAM_NS = "http://www.clarin.eu/cmd/"
BLAM_SCHEMA = "https://infra.clarin.eu/CMDI/1.x/xsd/cmd-component.xsd"
EMPTY_CMD = f'<CMD xmlns="{BLAM_NS}" CMDVersion="1.1"/>'


class BLAMSerializer:
    """Serializer for BLAM (CMDI) metadata format."""

    prefix = "blam"
    returns_string = True  # Indicates this serializer returns XML strings

    def __init__(self):
        self._collection_exporter = CollectionExporter()
        self._bundle_exporter = BundleExporter()

    def serialize(self, record: Mapping[str, object]) -> str:
        """Serialize collection or bundle to BLAM XML string."""
        bundle_id = record.get("BundleID")
        if bundle_id:
            bundle = self._fetch_bundle(bundle_id)
            if bundle:
                return self._bundle_exporter.export(bundle)
            return EMPTY_CMD

        collection_id = record.get("CollectionID")
        if not collection_id:
            return EMPTY_CMD

        collection = self._fetch_collection(collection_id)
        if not collection:
            return EMPTY_CMD

        return self._collection_exporter.export(collection)

    def _fetch_collection(self, identifier: str) -> Collection | None:
        """Fetch collection by identifier with prefetched relations."""
        return (
            Collection.objects.filter(identifier=identifier)
            .prefetch_related(
                "header",
                "general_info",
                "general_info__location",
                "general_info__keywords",
                "general_info__object_languages",
                "general_info__object_languages__alternative_names",
                "publication_info",
                "publication_info__creators",
                "publication_info__contributors",
                "administrative_info",
                "administrative_info__is_identical_to",
                "administrative_info__licenses",
                "administrative_info__rights_holders",
                "administrative_info__rights_holders__rights_holder_identifiers",
            )
            .first()
        )

    def _fetch_bundle(self, identifier: str) -> Bundle | None:
        """Fetch bundle by identifier with prefetched relations."""
        return (
            Bundle.objects.filter(identifier=identifier)
            .prefetch_related(
                "header",
                "general_info",
                "general_info__location",
                "general_info__keywords",
                "general_info__object_languages",
                "general_info__object_languages__alternative_names",
                "publication_info",
                "publication_info__creators",
                "publication_info__contributors",
                "administrative_info",
                "administrative_info__is_identical_to",
                "administrative_info__licenses",
                "administrative_info__rights_holders",
                "administrative_info__rights_holders__rights_holder_identifiers",
                "structural_info",
            )
            .first()
        )



def serialize(record: Mapping[str, object]) -> str:
    """Convenience function for serialization."""
    return BLAMSerializer().serialize(record)
