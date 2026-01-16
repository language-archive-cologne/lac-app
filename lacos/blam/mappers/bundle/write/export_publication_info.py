"""Export bundle publication info to BLAM schema."""

from typing import Optional
from django.db.models import QuerySet
from xsdata.models.datatype import XmlPeriod

from lacos.blam.models.base_indentifiers import PersonIdentifierTypeChoices
from blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd,
    CreatorNameIdentifierIdentifierType,
    ContributorNameIdentifierIdentifierType
)
from lacos.blam.models.bundle.bundle_publication_info import (
    BundlePublicationInfo,
    BundleCreator,
    BundleContributor,
)

# Type aliases for nested classes from the schema
BundlePublicationInfoType = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo
BundleCreatorsType = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators
BundleCreatorType = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators.BundleCreator
CreatorNameIdentifierType = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators.BundleCreator.CreatorNameIdentifier
CreatorNameType = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators.BundleCreator.CreatorName
BundleContributorsType = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors
BundleContributorType = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors.BundleContributor
ContributorNameIdentifierType = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors.BundleContributor.ContributorNameIdentifier
ContributorNameType = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors.BundleContributor.ContributorName


def export_publication_info(publication_info: BundlePublicationInfo, cmd_data: Cmd) -> None:
    """Export bundle publication information from Django models to BLAM schema."""
    bundle_info = BundlePublicationInfoType()

    bundle_info.bundle_publication_year = XmlPeriod(str(publication_info.publication_year))
    bundle_info.bundle_data_provider = publication_info.data_provider
    bundle_info.bundle_creators = export_creators(publication_info.creators.all())

    if publication_info.contributors.exists():
        bundle_info.bundle_contributors = export_contributors(publication_info.contributors.all())

    cmd_data.components.blam_bundle_repository_v1_0.bundle_publication_info = bundle_info


def export_creators(creators: QuerySet) -> BundleCreatorsType:
    """Export creators to schema format."""
    creators_data = BundleCreatorsType()
    creators_data.bundle_creator = [export_creator(creator) for creator in creators]
    return creators_data


def export_creator(creator: BundleCreator) -> BundleCreatorType:
    """Export a single creator to schema format."""
    creator_data = BundleCreatorType()

    # Set creator name
    creator_name = CreatorNameType()
    creator_name.creator_family_name = creator.family_name
    if creator.given_name:
        creator_name.creator_given_name = creator.given_name
    creator_data.creator_name = creator_name

    # Set identifier if present
    if creator.name_identifier:
        identifier = CreatorNameIdentifierType()
        identifier.value = creator.name_identifier
        identifier.identifier_type = _map_creator_identifier_type(creator.name_identifier_type)
        creator_data.creator_name_identifier = [identifier]

    # Set affiliation if present
    if creator.affiliation:
        creator_data.creator_affiliation = [creator.affiliation]

    return creator_data


def _map_creator_identifier_type(id_type: Optional[str]) -> CreatorNameIdentifierIdentifierType:
    """Map model identifier type to schema enum."""
    if id_type == PersonIdentifierTypeChoices.ORCID:
        return CreatorNameIdentifierIdentifierType.ORCID
    elif id_type == PersonIdentifierTypeChoices.ISNI:
        return CreatorNameIdentifierIdentifierType.ISNI
    elif id_type == PersonIdentifierTypeChoices.EMAIL:
        return CreatorNameIdentifierIdentifierType.EMAIL
    return CreatorNameIdentifierIdentifierType.OTHER


def export_contributors(contributors: QuerySet) -> BundleContributorsType:
    """Export contributors to schema format."""
    contributors_data = BundleContributorsType()
    contributors_data.bundle_contributor = [export_contributor(c) for c in contributors]
    return contributors_data


def export_contributor(contributor: BundleContributor) -> BundleContributorType:
    """Export a single contributor to schema format."""
    contributor_data = BundleContributorType()

    # Set contributor name - use contributor_name FK if available, otherwise base fields
    contributor_name = ContributorNameType()
    if hasattr(contributor, 'contributor_name') and contributor.contributor_name:
        contributor_name.contributor_family_name = contributor.contributor_name.contributor_family_name
        contributor_name.contributor_given_name = contributor.contributor_name.contributor_given_name
    else:
        contributor_name.contributor_family_name = contributor.family_name
        if contributor.given_name:
            contributor_name.contributor_given_name = contributor.given_name
    contributor_data.contributor_name = contributor_name

    # Set identifier if present
    if contributor.name_identifier:
        identifier = ContributorNameIdentifierType()
        identifier.value = contributor.name_identifier
        identifier.identifier_type = _map_contributor_identifier_type(contributor.name_identifier_type)
        contributor_data.contributor_name_identifier = [identifier]

    # Set affiliation if present
    if contributor.affiliation:
        contributor_data.contributor_affiliation = [contributor.affiliation]

    # Set role if present
    if contributor.role:
        contributor_data.contributor_role = [contributor.role]

    return contributor_data


def _map_contributor_identifier_type(id_type: Optional[str]) -> ContributorNameIdentifierIdentifierType:
    """Map model identifier type to schema enum."""
    if id_type == PersonIdentifierTypeChoices.ORCID:
        return ContributorNameIdentifierIdentifierType.ORCID
    elif id_type == PersonIdentifierTypeChoices.ISNI:
        return ContributorNameIdentifierIdentifierType.ISNI
    elif id_type == PersonIdentifierTypeChoices.EMAIL:
        return ContributorNameIdentifierIdentifierType.EMAIL
    return ContributorNameIdentifierIdentifierType.OTHER
