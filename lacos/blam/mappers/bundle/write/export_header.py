"""Export bundle header to BLAM schema."""

from xsdata.models.datatype import XmlDate

from blam_schemas.bundle.blam_bundle_repository_v1_1 import Cmd
from lacos.blam.models.bundle.bundle_header import BundleHeader

HeaderType = Cmd.Header
MdCreatorType = Cmd.Header.MdCreator
MdCreationDateType = Cmd.Header.MdCreationDate
MdSelfLinkType = Cmd.Header.MdSelfLink
MdProfileType = Cmd.Header.MdProfile
MdCollectionDisplayNameType = Cmd.Header.MdCollectionDisplayName


def export_header(header: BundleHeader, cmd: Cmd) -> None:
    """Export bundle header to BLAM CMD schema."""
    header_data = HeaderType()

    header_data.md_creator = [_create_md_creator(header.md_creator)]
    header_data.md_creation_date = _create_md_creation_date(header.md_creation_date)
    header_data.md_self_link = _create_md_self_link(header.md_self_link)
    header_data.md_profile = _create_md_profile(header.md_profile)

    cmd.header = header_data


def _create_md_creator(value: str) -> MdCreatorType:
    creator = MdCreatorType()
    creator.value = value
    return creator


def _create_md_creation_date(date_value) -> MdCreationDateType:
    creation_date = MdCreationDateType()
    if date_value:
        creation_date.value = XmlDate.from_date(date_value)
    return creation_date


def _create_md_self_link(value: str) -> MdSelfLinkType:
    self_link = MdSelfLinkType()
    self_link.value = value
    return self_link


def _create_md_profile(value: str) -> MdProfileType:
    profile = MdProfileType()
    profile.value = value
    return profile
