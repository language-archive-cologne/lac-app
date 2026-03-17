from dataclasses import dataclass
from typing import Any
import io
import logging
import unicodedata
import uuid
import xml.etree.ElementTree as ET

from django.core.exceptions import ValidationError
from django.db import transaction
from xsdata.formats.dataclass.models.generics import AnyElement
from xsdata.formats.dataclass.parsers import XmlParser

from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd as CmdV10
from blam_schemas.collection.blam_collection_repository_v1_2 import Cmd as CmdV12
from blam_schemas.collection.blam_collection_repository_v1_1 import (
    BlamCollectionRepositoryV11,
)
from blam_schemas.collection.cmd_envelop import Cmd as EnvelopeCmd
from lacos.blam.models.collection.collection_repository import Collection

# Import the standalone import functions
from lacos.blam.mappers.collection.read.import_collection_administrative_info import (
    import_administrative_info,
)
from lacos.blam.mappers.collection.read.import_collection_general_info import (
    import_general_info,
)
from lacos.blam.mappers.collection.read.import_collection_header import import_collection_header
from lacos.blam.mappers.collection.read.import_collection_project_info import (
    import_project_info,
)
from lacos.blam.mappers.collection.read.import_collection_publication_info import (
    import_publication_info,
)
from lacos.blam.mappers.collection.read.import_collection_structural_info import (
    import_structural_info,
)

logger = logging.getLogger(__name__)

BLAM_VERSION_1_0 = "1.0"
BLAM_VERSION_1_1 = "1.1"
BLAM_VERSION_1_2 = "1.2"


@dataclass
class CollectionComponentsAdapter:
    """Expose repository component under legacy attribute names expected by mappers."""

    repository: Any
    version: str

    def __getattr__(self, name: str) -> Any:
        if name in {
            "blam_collection_repository_v1_2",
            "blam_collection_repository_v1_1",
            "blam_collection_repository_v1_0",
        }:
            return self.repository
        raise AttributeError(name)


@dataclass
class CollectionCmdAdapter:
    """Container for parsed BLAM collection data and version metadata."""

    header: Any
    components: CollectionComponentsAdapter
    version: str


class CollectionImporter:
    """Handles importing BLAM Collection XML into Django models."""

    @staticmethod
    def validate_xml(xml_content: str) -> CollectionCmdAdapter:
        """Parse BLAM collection XML across supported schema versions."""
        # Normalize to Unicode NFC for consistent character representation
        xml_content = unicodedata.normalize("NFC", xml_content)

        version = CollectionImporter._detect_version(xml_content)
        logger.debug("Detected BLAM collection version %s", version)
        if version == BLAM_VERSION_1_2:
            return CollectionImporter._parse_v12(xml_content)
        if version == BLAM_VERSION_1_0:
            return CollectionImporter._parse_v10(xml_content)
        if version == BLAM_VERSION_1_1:
            return CollectionImporter._parse_v11(xml_content)
        raise ValidationError(f"Unsupported BLAM collection version: {version}")

    @classmethod
    @transaction.atomic
    def import_from_xml(cls, xml_content: str, update_existing: bool = False) -> Collection:
        """Import a collection from XML content."""
        cmd_data = cls.validate_xml(xml_content)

        md_self_link = None
        if cmd_data.header and getattr(cmd_data.header, "md_self_link", None):
            md_self_link = cmd_data.header.md_self_link.value

            existing_collection = Collection.objects.filter(identifier=md_self_link).first()
            if existing_collection:
                logger.info(
                    "Found existing collection with identifier %s",
                    md_self_link,
                )
                if existing_collection.source_version != cmd_data.version:
                    existing_collection.source_version = cmd_data.version
                    existing_collection.save(update_fields=["source_version"])
                if not update_existing:
                    logger.info("Update mode disabled; returning without changes.")
                    return existing_collection
                return cls._update_existing_collection(existing_collection, cmd_data)

        collection = cls._import_cmd_to_models(cmd_data)

        update_fields = ["source_version"]
        if md_self_link:
            collection.identifier = md_self_link
            update_fields.append("identifier")
        collection.source_version = cmd_data.version
        collection.save(update_fields=update_fields)

        logger.info(
            "Collection import completed for '%s' (version %s).",
            md_self_link,
            cmd_data.version,
        )
        return collection

    @classmethod
    def _update_existing_collection(
        cls, collection: Collection, cmd_data: CollectionCmdAdapter
    ) -> Collection:
        """Update an existing collection in place."""
        try:
            cls._import_header(cmd_data, collection)
            cls._import_general_info(cmd_data, collection)
            cls._import_publication_info(cmd_data, collection)
            cls._import_administrative_info(cmd_data, collection)
            cls._import_structural_info(cmd_data, collection)

            repository = getattr(cmd_data.components, "blam_collection_repository_v1_2", None)
            if repository is not None:
                project_infos = cls._import_project_info(cmd_data, collection)
                if project_infos:
                    logger.info("Project info found and imported for update")
                else:
                    logger.info("No project info found in XML - existing links cleared")

            update_fields = []
            md_self_link = None
            if cmd_data.header and getattr(cmd_data.header, "md_self_link", None):
                md_self_link = cmd_data.header.md_self_link.value
            if md_self_link and collection.identifier != md_self_link:
                collection.identifier = md_self_link
                update_fields.append("identifier")
            if collection.source_version != cmd_data.version:
                collection.source_version = cmd_data.version
                update_fields.append("source_version")
            if update_fields:
                collection.save(update_fields=update_fields)

            logger.info(
                "Collection update completed for '%s' (version %s).",
                md_self_link or collection.identifier,
                cmd_data.version,
            )
            return collection
        except Exception as exc:  # pragma: no cover - re-raise for transaction rollback
            logger.error("Error during collection update: %s", exc, exc_info=True)
            raise

    @classmethod
    def _import_cmd_to_models(cls, cmd_data: CollectionCmdAdapter) -> Collection:
        """Convert parsed data into Django models."""
        collection = cls._create_collection()

        try:
            cls._import_header(cmd_data, collection)
            cls._import_general_info(cmd_data, collection)
            cls._import_publication_info(cmd_data, collection)
            cls._import_administrative_info(cmd_data, collection)
            cls._import_structural_info(cmd_data, collection)

            repository = getattr(cmd_data.components, "blam_collection_repository_v1_2", None)
            if repository is not None:
                project_infos = cls._import_project_info(cmd_data, collection)
                if project_infos:
                    logger.info("Project info found and imported")
                else:
                    logger.info("No project info found in XML")

            return collection

        except Exception as exc:  # pragma: no cover - re-raise for transaction rollback
            logger.error("Error during collection import: %s", exc, exc_info=True)
            raise

    @classmethod
    def _create_collection(cls) -> Collection:
        """Create a new collection placeholder before components import."""
        collection = Collection.objects.create(identifier=f"temp-collection-{uuid.uuid4()}")
        logger.info("Created new Collection with ID %s", collection.id)
        return collection

    @classmethod
    def _import_header(cls, cmd_data: CollectionCmdAdapter, collection: Collection):
        header = import_collection_header(cmd_data, collection)
        logger.info("Imported header for collection %s", collection.id)
        return header

    @classmethod
    def _import_general_info(cls, cmd_data: CollectionCmdAdapter, collection: Collection):
        general_info = import_general_info(cmd_data, collection)
        logger.info("Imported general info for collection %s", collection.id)
        return general_info

    @classmethod
    def _import_publication_info(cls, cmd_data: CollectionCmdAdapter, collection: Collection):
        publication_info = import_publication_info(cmd_data, collection)
        logger.info("Imported publication info for collection %s", collection.id)
        return publication_info

    @classmethod
    def _import_project_info(cls, cmd_data: CollectionCmdAdapter, collection: Collection):
        project_info = import_project_info(cmd_data, collection)
        logger.info("Imported project info for collection %s", collection.id)
        return project_info

    @classmethod
    def _import_administrative_info(
        cls, cmd_data: CollectionCmdAdapter, collection: Collection
    ):
        administrative_info = import_administrative_info(cmd_data, collection)
        logger.info("Imported administrative info for collection %s", collection.id)
        return administrative_info

    @classmethod
    def _import_structural_info(cls, cmd_data: CollectionCmdAdapter, collection: Collection):
        structural_info = import_structural_info(cmd_data, collection)
        logger.info("Imported structural info for collection %s", collection.id)
        return structural_info

    @staticmethod
    def _detect_version(xml_content: str) -> str:
        try:
            for _, element in ET.iterparse(io.StringIO(xml_content), events=("start",)):
                local = element.tag.split("}")[-1]
                if local.startswith("BLAM-collection-repository"):
                    if "v1.2" in local or "v1_2" in local:
                        return BLAM_VERSION_1_2
                    if "v1.1" in local or "v1_1" in local:
                        return BLAM_VERSION_1_1
                    return BLAM_VERSION_1_0
                element.clear()
        except ET.ParseError as exc:  # pragma: no cover - propagate as validation error
            raise ValidationError(f"Invalid BLAM collection XML: {exc}") from exc
        return BLAM_VERSION_1_0

    @staticmethod
    def _parse_v10(xml_content: str) -> CollectionCmdAdapter:
        try:
            parser = XmlParser()
            cmd = parser.from_string(xml_content, CmdV10)
        except Exception as exc:  # pragma: no cover - xsdata validation
            raise ValidationError(f"Invalid BLAM collection XML: {exc}") from exc

        repository = getattr(cmd.components, "blam_collection_repository_v1_0", None)
        components = CollectionComponentsAdapter(repository=repository, version=BLAM_VERSION_1_0)
        return CollectionCmdAdapter(header=cmd.header, components=components, version=BLAM_VERSION_1_0)

    @staticmethod
    def _parse_v12(xml_content: str) -> CollectionCmdAdapter:
        try:
            parser = XmlParser()
            cmd = parser.from_string(xml_content, CmdV12)
        except Exception as exc:  # pragma: no cover - xsdata validation
            raise ValidationError(f"Invalid BLAM collection XML: {exc}") from exc

        repository = getattr(cmd.components, "blam_collection_repository_v1_2", None)
        components = CollectionComponentsAdapter(repository=repository, version=BLAM_VERSION_1_2)
        return CollectionCmdAdapter(header=cmd.header, components=components, version=BLAM_VERSION_1_2)

    @staticmethod
    def _parse_v11(xml_content: str) -> CollectionCmdAdapter:
        parser = XmlParser()
        try:
            envelope = parser.from_string(xml_content, EnvelopeCmd)
        except Exception as exc:  # pragma: no cover - xsdata validation
            raise ValidationError(f"Invalid BLAM collection XML: {exc}") from exc

        repository = CollectionImporter._deserialize_repository(parser, envelope)
        components = CollectionComponentsAdapter(repository=repository, version=BLAM_VERSION_1_1)
        return CollectionCmdAdapter(header=envelope.header, components=components, version=BLAM_VERSION_1_1)

    @staticmethod
    def _deserialize_repository(parser: XmlParser, envelope: EnvelopeCmd) -> Any:
        other_element = getattr(envelope.components, "other_element", None)
        if isinstance(other_element, BlamCollectionRepositoryV11):
            return other_element
        if not isinstance(other_element, AnyElement):
            raise ValidationError("BLAM collection XML missing repository component")
        element = CollectionImporter._any_element_to_element(other_element)
        fragment = ET.tostring(element, encoding="unicode")
        try:
            return parser.from_string(fragment, BlamCollectionRepositoryV11)
        except Exception as exc:  # pragma: no cover - xsdata validation
            raise ValidationError(f"Invalid BLAM collection component: {exc}") from exc

    @staticmethod
    def _any_element_to_element(any_element: AnyElement) -> ET.Element:
        qname = any_element.qname or ""
        tag = qname if qname.startswith("{") else qname
        element = ET.Element(tag)
        for attr, value in any_element.attributes.items():
            element.set(attr, value)
        if any_element.text:
            element.text = any_element.text
        for child in any_element.children:
            element.append(CollectionImporter._any_element_to_element(child))
        return element
