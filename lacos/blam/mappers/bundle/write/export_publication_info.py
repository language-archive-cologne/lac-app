from typing import Dict, Any, List, Optional
from django.db.models import QuerySet
from xsdata.models.datatype import XmlPeriod
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd,
    CreatorNameIdentifierIdentifierType,
    ContributorNameIdentifierIdentifierType
)
from lacos.blam.models.bundle.bundle_publication_info import (
    BundlePublicationInfo,
    BundleCreator,
    BundleCreatorNameIdentifier,
    BundleCreatorName,
    BundleContributor,
    BundleContributorNameIdentifier,
    BundleContributorName
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
    """
    Export bundle publication information from Django models to BLAM schema.
    
    Args:
        publication_info: The BundlePublicationInfo instance to export
        cmd_data: The BLAM bundle repository schema data to populate
    """
    # Create the bundle publication info structure
    bundle_info = BundlePublicationInfoType()
    
    # Set publication year
    bundle_info.bundle_publication_year = XmlPeriod(publication_info.publication_year)
    
    # Set data provider
    bundle_info.bundle_data_provider = publication_info.data_provider
    
    # Set creators
    bundle_info.bundle_creators = export_creators(publication_info.creators.all())
    
    # Set contributors if present
    if publication_info.contributors.exists():
        bundle_info.bundle_contributors = export_contributors(publication_info.contributors.all())
    
    # Assign to cmd_data
    cmd_data.components.blam_bundle_repository_v1_0.bundle_publication_info = bundle_info


def export_creators(creators: QuerySet) -> BundleCreatorsType:
    """
    Export creators to schema format.
    
    Args:
        creators: QuerySet of BundleCreator instances
        
    Returns:
        A creators container for the schema
    """
    creators_data = BundleCreatorsType()
    creators_data.bundle_creator = [
        export_creator(creator) for creator in creators
    ]
    return creators_data


def export_creator(creator: BundleCreator) -> BundleCreatorType:
    """
    Export a single creator to schema format.
    
    Args:
        creator: The BundleCreator instance
        
    Returns:
        A creator object for the schema
    """
    creator_data = BundleCreatorType()
    
    # Set creator name
    creator_data.creator_name = export_creator_name(creator.name)
    
    # Set creator identifiers if present
    if creator.identifiers.exists():
        creator_data.creator_name_identifier = [
            export_creator_identifier(identifier) for identifier in creator.identifiers.all()
        ]
    
    # Set affiliations if present
    if creator.affiliations.exists():
        creator_data.creator_affiliation = [
            affiliation.value for affiliation in creator.affiliations.all()
        ]
    
    # Set order if present
    if creator.order is not None:
        creator_data.order = creator.order
    
    return creator_data


def export_creator_name(name: BundleCreatorName) -> CreatorNameType:
    """
    Export a creator name to schema format.
    
    Args:
        name: The BundleCreatorName instance
        
    Returns:
        A creator name object for the schema
    """
    name_data = CreatorNameType()
    name_data.creator_family_name = name.family_name
    
    if name.given_name:
        name_data.creator_given_name = name.given_name
    
    return name_data


def export_creator_identifier(identifier: BundleCreatorNameIdentifier) -> CreatorNameIdentifierType:
    """
    Export a creator identifier to schema format.
    
    Args:
        identifier: The BundleCreatorNameIdentifier instance
        
    Returns:
        A creator identifier object for the schema
    """
    identifier_data = CreatorNameIdentifierType()
    identifier_data.value = identifier.value
    
    # Determine identifier type based on the URL
    identifier_data.identifier_type = determine_creator_identifier_type(identifier.value)
    
    return identifier_data


def determine_creator_identifier_type(url: str) -> CreatorNameIdentifierIdentifierType:
    """
    Determine the creator identifier type based on the URL.
    
    Args:
        url: The identifier URL
        
    Returns:
        The corresponding identifier type enum value
    """
    if "orcid.org" in url.lower():
        return CreatorNameIdentifierIdentifierType.ORCID
    elif "isni.org" in url.lower():
        return CreatorNameIdentifierIdentifierType.ISNI
    elif "@" in url:
        return CreatorNameIdentifierIdentifierType.EMAIL
    else:
        return CreatorNameIdentifierIdentifierType.OTHER


def export_contributors(contributors: QuerySet) -> BundleContributorsType:
    """
    Export contributors to schema format.
    
    Args:
        contributors: QuerySet of BundleContributor instances
        
    Returns:
        A contributors container for the schema
    """
    contributors_data = BundleContributorsType()
    contributors_data.bundle_contributor = [
        export_contributor(contributor) for contributor in contributors
    ]
    return contributors_data


def export_contributor(contributor: BundleContributor) -> BundleContributorType:
    """
    Export a single contributor to schema format.
    
    Args:
        contributor: The BundleContributor instance
        
    Returns:
        A contributor object for the schema
    """
    contributor_data = BundleContributorType()
    
    # Set contributor name
    contributor_data.contributor_name = export_contributor_name(contributor.name)
    
    # Set contributor identifiers if present
    if contributor.identifiers.exists():
        contributor_data.contributor_name_identifier = [
            export_contributor_identifier(identifier) for identifier in contributor.identifiers.all()
        ]
    
    # Set affiliations if present
    if contributor.affiliations.exists():
        contributor_data.contributor_affiliation = [
            affiliation.value for affiliation in contributor.affiliations.all()
        ]
    
    # Set roles if present
    if contributor.roles.exists():
        contributor_data.contributor_role = [
            role.value for role in contributor.roles.all()
        ]
    
    return contributor_data


def export_contributor_name(name: BundleContributorName) -> ContributorNameType:
    """
    Export a contributor name to schema format.
    
    Args:
        name: The BundleContributorName instance
        
    Returns:
        A contributor name object for the schema
    """
    name_data = ContributorNameType()
    name_data.contributor_family_name = name.family_name
    
    if name.given_name:
        name_data.contributor_given_name = name.given_name
    
    return name_data


def export_contributor_identifier(identifier: BundleContributorNameIdentifier) -> ContributorNameIdentifierType:
    """
    Export a contributor identifier to schema format.
    
    Args:
        identifier: The BundleContributorNameIdentifier instance
        
    Returns:
        A contributor identifier object for the schema
    """
    identifier_data = ContributorNameIdentifierType()
    identifier_data.value = identifier.value
    
    # Determine identifier type based on the URL
    identifier_data.identifier_type = determine_contributor_identifier_type(identifier.value)
    
    return identifier_data


def determine_contributor_identifier_type(url: str) -> ContributorNameIdentifierIdentifierType:
    """
    Determine the contributor identifier type based on the URL.
    
    Args:
        url: The identifier URL
        
    Returns:
        The corresponding identifier type enum value
    """
    if "orcid.org" in url.lower():
        return ContributorNameIdentifierIdentifierType.ORCID
    elif "isni.org" in url.lower():
        return ContributorNameIdentifierIdentifierType.ISNI
    elif "@" in url:
        return ContributorNameIdentifierIdentifierType.EMAIL
    else:
        return ContributorNameIdentifierIdentifierType.OTHER
