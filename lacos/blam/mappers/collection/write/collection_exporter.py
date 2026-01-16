"""Main collection exporter for BLAM XML serialization."""

from xml.etree import ElementTree as ET

from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd
from lacos.blam.models.collection.collection_repository import Collection

from .export_header import export_header
from .export_general_info import export_general_info
from .export_publication_info import export_publication_info
from .export_administrative_info import export_administrative_info

CMD_NAMESPACE = "http://www.clarin.eu/cmd/"
NS_MAP = {"": CMD_NAMESPACE}


class CollectionExporter:
    """Exports a Collection model to BLAM XML."""

    def __init__(self):
        config = SerializerConfig(
            pretty_print=True,
            xml_declaration=False,
        )
        self._serializer = XmlSerializer(config=config)

    def export(self, collection: Collection) -> str:
        """Export collection to BLAM XML string (with default CMD namespace)."""
        cmd = self._build_cmd(collection)
        return self._serializer.render(cmd, ns_map=NS_MAP)

    def export_to_xml_string(self, collection: Collection) -> str:
        """Export collection to XML string for OAI-PMH embedding."""
        return self.export(collection)

    def export_to_element(self, collection: Collection) -> ET.Element:
        """Export collection to XML Element."""
        xml_str = self.export(collection)
        return ET.fromstring(xml_str)

    def _build_cmd(self, collection: Collection) -> Cmd:
        """Build the CMD dataclass from collection model."""
        cmd = Cmd()

        # Initialize required structures
        cmd.header = Cmd.Header()
        cmd.resources = self._create_empty_resources()
        cmd.components = Cmd.Components()
        cmd.components.blam_collection_repository_v1_0 = (
            Cmd.Components.BlamCollectionRepositoryV10()
        )

        repo = cmd.components.blam_collection_repository_v1_0

        # Export header
        header = collection.header.first()
        if header:
            export_header(header, cmd)

        # Export general info
        general_info = collection.general_info.first()
        if general_info:
            export_general_info(general_info, repo)

        # Export publication info
        pub_info = collection.publication_info.first()
        if pub_info:
            export_publication_info(pub_info, repo)

        # Export administrative info
        admin_info = collection.administrative_info.first()
        if admin_info:
            export_administrative_info(admin_info, repo)

        # Set MD license (from admin info if available)
        repo.mdlicense = self._create_md_license(admin_info)

        # Structural info (empty for now, bundles handled separately)
        repo.collection_structural_info = self._create_empty_structural_info()

        return cmd

    def _create_empty_resources(self) -> Cmd.Resources:
        """Create empty resources section."""
        resources = Cmd.Resources()
        resources.resource_proxy_list = Cmd.Resources.ResourceProxyList()
        resources.journal_file_proxy_list = Cmd.Resources.JournalFileProxyList()
        resources.resource_relation_list = Cmd.Resources.ResourceRelationList()
        return resources

    def _create_md_license(self, admin_info) -> Cmd.Components.BlamCollectionRepositoryV10.Mdlicense:
        """Create MD license from administrative info."""
        md_license = Cmd.Components.BlamCollectionRepositoryV10.Mdlicense()
        if admin_info and admin_info.licenses.exists():
            first_license = admin_info.licenses.first()
            md_license.value = first_license.license_name
            md_license.uri = first_license.license_identifier
        else:
            md_license.value = "Unknown"
        return md_license

    def _create_empty_structural_info(self):
        """Create empty structural info section."""
        struct_info = Cmd.Components.BlamCollectionRepositoryV10.CollectionStructuralInfo()
        struct_info.collection_members = (
            Cmd.Components.BlamCollectionRepositoryV10.CollectionStructuralInfo.CollectionMembers()
        )
        return struct_info
