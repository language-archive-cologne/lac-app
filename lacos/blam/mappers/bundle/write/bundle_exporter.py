"""Main bundle exporter for BLAM XML serialization."""

from xml.etree import ElementTree as ET

from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from blam_schemas.bundle.blam_bundle_repository_v1_1 import Cmd, ResourcetypeSimple
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources

from .export_header import export_header
from .export_general_info import export_general_info
from .export_publication_info import export_publication_info
from .export_administrative_info import export_administrative_info
from .export_structural_info import export_structural_info

CMD_NAMESPACE = "http://www.clarin.eu/cmd/"
NS_MAP = {"": CMD_NAMESPACE}


class BundleExporter:
    """Exports a Bundle model to BLAM XML."""

    def __init__(self):
        config = SerializerConfig(
            pretty_print=True,
            xml_declaration=False,
        )
        self._serializer = XmlSerializer(config=config)

    def export(self, bundle: Bundle) -> str:
        """Export bundle to BLAM XML string (with default CMD namespace)."""
        cmd = self._build_cmd(bundle)
        return self._serializer.render(cmd, ns_map=NS_MAP)

    def export_to_xml_string(self, bundle: Bundle) -> str:
        """Export bundle to XML string for OAI-PMH embedding."""
        return self.export(bundle)

    def export_to_element(self, bundle: Bundle) -> ET.Element:
        """Export bundle to XML Element."""
        xml_str = self.export(bundle)
        return ET.fromstring(xml_str)

    def _build_cmd(self, bundle: Bundle) -> Cmd:
        """Build the CMD dataclass from bundle model."""
        cmd = Cmd()

        # Initialize required structures
        cmd.header = Cmd.Header()
        cmd.resources = self._create_resources(bundle)
        cmd.components = Cmd.Components()
        cmd.components.blam_bundle_repository_v1_1 = (
            Cmd.Components.BlamBundleRepositoryV11()
        )

        # Export header
        header = bundle.header.first()
        if header:
            export_header(header, cmd)

        # Export general info
        general_info = bundle.general_info.first()
        if general_info:
            export_general_info(general_info, cmd)

        # Export publication info
        pub_info = bundle.publication_info.first()
        if pub_info:
            export_publication_info(pub_info, cmd)

        # Export administrative info
        admin_info = bundle.administrative_info.first()
        if admin_info:
            export_administrative_info(admin_info, cmd)

        # Export structural info
        structural_info = bundle.structural_info.first()
        if structural_info:
            export_structural_info(structural_info, cmd)

        # Set MD license (from admin info if available)
        repo = cmd.components.blam_bundle_repository_v1_1
        repo.mdlicense = self._create_md_license(admin_info)

        return cmd

    def _create_resources(self, bundle: Bundle) -> Cmd.Resources:
        """Create the resources section with a ResourceProxy per file.

        One ``Resource`` proxy per media/written/other file (referencing its
        ``file_pid``), plus a ``LandingPage`` proxy to the bundle's own handle so
        every bundle exposes at least one proxy (a VLO minimum requirement).
        """
        resources = Cmd.Resources()
        proxy_list = Cmd.Resources.ResourceProxyList()
        resources.resource_proxy_list = proxy_list
        resources.journal_file_proxy_list = Cmd.Resources.JournalFileProxyList()
        resources.resource_relation_list = Cmd.Resources.ResourceRelationList()

        ResourceProxy = Cmd.Resources.ResourceProxyList.ResourceProxy
        ResourceType = ResourceProxy.ResourceType
        ResourceRef = ResourceProxy.ResourceRef

        idx = 0
        bundle_resources = BundleResources.objects.filter(bundle=bundle).first()
        if bundle_resources:
            files = [
                *bundle_resources.bundle_media_resources.all(),
                *bundle_resources.bundle_written_resources.all(),
                *bundle_resources.bundle_other_resources.all(),
            ]
            for resource in files:
                if not resource.file_pid:
                    continue
                idx += 1
                proxy_list.resource_proxy.append(ResourceProxy(
                    resource_type=ResourceType(
                        value=ResourcetypeSimple.RESOURCE,
                        mimetype=resource.mime_type or None,
                    ),
                    resource_ref=ResourceRef(value=resource.file_pid),
                    id=f"d{idx}",
                ))

        if bundle.identifier:
            proxy_list.resource_proxy.append(ResourceProxy(
                resource_type=ResourceType(value=ResourcetypeSimple.LANDING_PAGE),
                resource_ref=ResourceRef(value=bundle.identifier),
                id="lp1",
            ))

        return resources

    def _create_md_license(self, admin_info) -> Cmd.Components.BlamBundleRepositoryV11.Mdlicense:
        """Create MD license from administrative info."""
        md_license = Cmd.Components.BlamBundleRepositoryV11.Mdlicense()
        if admin_info and admin_info.licenses.exists():
            first_license = admin_info.licenses.first()
            md_license.value = first_license.license_name
            md_license.uri = first_license.license_identifier
        else:
            md_license.value = "Unknown"
        return md_license
