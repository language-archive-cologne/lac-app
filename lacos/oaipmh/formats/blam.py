"""BLAM metadata serializer for OAI-PMH."""

from __future__ import annotations

from typing import Iterable, Mapping

from django.db.models import QuerySet

from lacos.blam.mappers.collection.write import CollectionExporter
from lacos.blam.mappers.bundle.write import BundleExporter
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle

BLAM_NS = "http://www.clarin.eu/cmd/"
BLAM_SCHEMA = "https://infra.clarin.eu/CMDI/1.x/xsd/cmd-component.xsd"
EMPTY_CMD = f'<CMD xmlns="{BLAM_NS}" CMDVersion="1.1"/>'

COLLECTION_PREFETCHES = (
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

BUNDLE_PREFETCHES = COLLECTION_PREFETCHES + (
    "structural_info",
    "structural_info__additional_metadata_files",
    "structural_info__is_member_of_collection__general_info",
    "resources__bundle_media_resources",
    "resources__bundle_written_resources__annotations",
    "resources__bundle_other_resources",
)


class BLAMSerializer:
    """Serializer for BLAM (CMDI) metadata format."""

    prefix = "blam"
    returns_string = True  # Indicates this serializer returns XML strings

    def __init__(self):
        self._collection_exporter = CollectionExporter()
        self._bundle_exporter = BundleExporter()

    def serialize(self, record: Mapping[str, object]) -> str:
        """Serialize a single collection or bundle to a BLAM XML string."""
        return self.serialize_many([record])[0]

    def serialize_many(self, records: Iterable[Mapping[str, object]]) -> list[str]:
        """Serialize a page of records, batch-fetching their models."""
        records = list(records)
        bundle_ids = {
            record["BundleID"] for record in records if record.get("BundleID")
        }
        collection_ids = {
            record["CollectionID"]
            for record in records
            if not record.get("BundleID") and record.get("CollectionID")
        }

        bundles = {
            bundle.identifier: bundle
            for bundle in self._bundle_queryset(bundle_ids)
        }
        collections = {
            collection.identifier: collection
            for collection in self._collection_queryset(collection_ids)
        }

        serialized: list[str] = []
        for record in records:
            bundle_id = record.get("BundleID")
            if bundle_id:
                bundle = bundles.get(bundle_id)
                serialized.append(
                    self._bundle_exporter.export(bundle) if bundle else EMPTY_CMD
                )
                continue

            collection = collections.get(record.get("CollectionID"))
            serialized.append(
                self._collection_exporter.export(collection) if collection else EMPTY_CMD
            )
        return serialized

    def _collection_queryset(self, identifiers: set[str]) -> QuerySet[Collection]:
        if not identifiers:
            return Collection.objects.none()
        return Collection.objects.filter(identifier__in=identifiers).prefetch_related(
            *COLLECTION_PREFETCHES
        )

    def _bundle_queryset(self, identifiers: set[str]) -> QuerySet[Bundle]:
        if not identifiers:
            return Bundle.objects.none()
        return Bundle.objects.filter(identifier__in=identifiers).prefetch_related(
            *BUNDLE_PREFETCHES
        )


def serialize(record: Mapping[str, object]) -> str:
    """Convenience function for serialization."""
    return BLAMSerializer().serialize(record)
