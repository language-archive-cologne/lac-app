"""Export collection header to BLAM schema."""

from xsdata.models.datatype import XmlDate

from blam_schemas.collection.blam_collection_repository_v1_2 import Cmd
from lacos.blam.models.collection.collection_header import CollectionHeader

HeaderType = Cmd.Header
MdCreatorType = Cmd.Header.MdCreator
MdCreationDateType = Cmd.Header.MdCreationDate
MdSelfLinkType = Cmd.Header.MdSelfLink
MdProfileType = Cmd.Header.MdProfile
MdCollectionDisplayNameType = Cmd.Header.MdCollectionDisplayName


def export_header(header: CollectionHeader, cmd: Cmd) -> None:
    """Export collection header to BLAM CMD schema."""
    header_data = HeaderType()

    header_data.md_creator = [_create_md_creator(header.md_creator)]
    header_data.md_creation_date = _create_md_creation_date(header.md_creation_date)
    header_data.md_self_link = _create_md_self_link(header.md_self_link)
    header_data.md_profile = _create_md_profile(header.md_profile)

    if header.md_collection_display_name:
        header_data.md_collection_display_name = _create_md_collection_display_name(
            header.md_collection_display_name
        )

    cmd.header = header_data


def _create_md_creator(value: str) -> MdCreatorType:
    creator = MdCreatorType()
    creator.value = value
    return creator


def _create_md_creation_date(date_value) -> MdCreationDateType:
    creation_date = MdCreationDateType()
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


def _create_md_collection_display_name(value: str) -> MdCollectionDisplayNameType:
    display_name = MdCollectionDisplayNameType()
    display_name.value = value
    return display_name
