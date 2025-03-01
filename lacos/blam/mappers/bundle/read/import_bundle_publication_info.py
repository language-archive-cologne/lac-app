from typing import Optional, List
from django.db import transaction
from lacos.blam.models.bundle.bundle_publication_info import (
    BundlePublicationInfo, BundleCreator, BundleContributor, BundleContributorName
)
from blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd, CreatorNameIdentifierIdentifierType, ContributorNameIdentifierIdentifierType
)


@transaction.atomic
def import_publication_info(cmd_data: Cmd) -> Optional[BundlePublicationInfo]:
    """
    Import publication info from CMD object to Django models.
    
    Args:
        cmd_data: The CMD object containing bundle publication information
        
    Returns:
        BundlePublicationInfo object or None if publication info is missing
    """
    components = cmd_data.components
    if not components or not components.blam_bundle_repository_v1_0:
        return None
        
    repo = components.blam_bundle_repository_v1_0
    pub_info = repo.bundle_publication_info
    if not pub_info:
        return None
        
    # Get or create publication info
    # Using publication_year and data_provider as unique identifiers
    bundle_pub_info, created = BundlePublicationInfo.objects.get_or_create(
        publication_year=pub_info.bundle_publication_year.value.year,
        data_provider=pub_info.bundle_data_provider
    )
    
    # Import creators
    if pub_info.bundle_creators:
        import_creators(bundle_pub_info, pub_info.bundle_creators.bundle_creator)
        
    # Import contributors
    if pub_info.bundle_contributors:
        import_contributors(bundle_pub_info, pub_info.bundle_contributors.bundle_contributor)
        
    return bundle_pub_info


def import_creators(bundle_pub_info: BundlePublicationInfo, creators_data: List) -> None:
    """
    Import creators from CMD data to Django models.
    
    Args:
        bundle_pub_info: The BundlePublicationInfo object to link creators to
        creators_data: List of creator data from the CMD object
    """
    for creator_data in creators_data:
        if not creator_data.creator_name:
            continue
            
        # Get or create creator using family_name and given_name as unique identifiers
        creator, created = BundleCreator.objects.get_or_create(
            family_name=creator_data.creator_name.creator_family_name,
            given_name=creator_data.creator_name.creator_given_name or "",
            defaults={
                'name_identifier': None,
                'name_identifier_type': None,
                'affiliation': None
            }
        )
        
        # Handle identifiers
        if creator_data.creator_name_identifier:
            for identifier in creator_data.creator_name_identifier:
                if identifier.identifier_type == CreatorNameIdentifierIdentifierType.ORCID:
                    creator.name_identifier = identifier.value
                    creator.name_identifier_type = "ORCID"
                    break
        
        # Handle affiliation
        if creator_data.creator_affiliation:
            creator.affiliation = creator_data.creator_affiliation[0]
            
        creator.save()
        bundle_pub_info.creators.add(creator)


def import_contributors(bundle_pub_info: BundlePublicationInfo, contributors_data: List) -> None:
    """
    Import contributors from CMD data to Django models.
    
    Args:
        bundle_pub_info: The BundlePublicationInfo object to link contributors to
        contributors_data: List of contributor data from the CMD object
    """
    for contributor_data in contributors_data:
        if not contributor_data.contributor_name:
            continue
                
        # Get or create contributor name
        contributor_name, name_created = BundleContributorName.objects.get_or_create(
            contributor_family_name=contributor_data.contributor_name.contributor_family_name,
            contributor_given_name=contributor_data.contributor_name.contributor_given_name or ""
        )
        
        # Get or create contributor
        contributor, created = BundleContributor.objects.get_or_create(
            contributor_name=contributor_name,
            family_name=contributor_data.contributor_name.contributor_family_name,
            given_name=contributor_data.contributor_name.contributor_given_name or "",
            defaults={
                'name_identifier': None,
                'name_identifier_type': None,
                'affiliation': None,
                'role': None
            }
        )
        
        # Handle identifiers
        if contributor_data.contributor_name_identifier:
            for identifier in contributor_data.contributor_name_identifier:
                if identifier.identifier_type == ContributorNameIdentifierIdentifierType.ORCID:
                    contributor.name_identifier = identifier.value
                    contributor.name_identifier_type = "ORCID"
                    break
        
        # Handle affiliation
        if contributor_data.contributor_affiliation:
            contributor.affiliation = contributor_data.contributor_affiliation[0]
                
        # Handle role
        if contributor_data.contributor_role:
            contributor.role = contributor_data.contributor_role[0]
                
        contributor.save()
        bundle_pub_info.contributors.add(contributor)
