from typing import Optional, List
from django.db import transaction
from lacos.blam.models.bundle.bundle_publication_info import (
    BundlePublicationInfo, BundlePublicationInfoCreator,
    BundleCreator, BundleContributor, BundleContributorName,
)
from blam_schemas.bundle.blam_bundle_repository_v1_1 import (
    Cmd,
    CreatorNameIdentifierIdentifierType,
    ContributorNameIdentifierIdentifierType,
)
from lacos.blam.models.base_indentifiers import PersonIdentifierTypeChoices
import logging

logger = logging.getLogger(__name__)

@transaction.atomic
def import_publication_info(cmd_data: Cmd, bundle: 'Bundle') -> Optional[BundlePublicationInfo]:
    """
    Import publication info from CMD object to Django models.
    
    Args:
        cmd_data: The CMD object containing bundle publication information
        bundle: The Bundle instance to associate the publication info with
        
    Returns:
        BundlePublicationInfo object or None if publication info is missing
    """
    components = cmd_data.components
    if not components or not components.blam_bundle_repository_v1_1:
        return None
        
    repo = components.blam_bundle_repository_v1_1
    pub_info = repo.bundle_publication_info
    if not pub_info:
        return None
    
    # Extract the publication year
    pub_year = None
    if hasattr(pub_info, 'bundle_publication_year'):
        # Try to extract publication year from XmlPeriod object
        try:
            # First, try to get the value directly if it's a string
            if isinstance(pub_info.bundle_publication_year, str):
                pub_year = int(pub_info.bundle_publication_year)
            # Otherwise, try to access year attribute
            elif hasattr(pub_info.bundle_publication_year, 'year'):
                pub_year = pub_info.bundle_publication_year.year
            # Try to access the value attribute if it's not a string but has a value attribute
            elif hasattr(pub_info.bundle_publication_year, 'value'):
                if hasattr(pub_info.bundle_publication_year.value, 'year'):
                    pub_year = pub_info.bundle_publication_year.value.year
                else:
                    pub_year = int(pub_info.bundle_publication_year.value)
        except (AttributeError, ValueError):
            # If all else fails, use default
            pub_year = 2018  # Default value based on XML

    # Get or create publication info using publication_year and data_provider as unique identifiers
    data_provider = pub_info.bundle_data_provider if hasattr(pub_info, 'bundle_data_provider') else None
    
    # Extract primary creator identifier and type for the main record
    primary_identifier = ''
    primary_identifier_type = PersonIdentifierTypeChoices.OTHER.value  # default to valid choice
    first_creator_data = None
    if hasattr(pub_info, 'bundle_creators') and pub_info.bundle_creators and pub_info.bundle_creators.bundle_creator:
        first_creator_data = pub_info.bundle_creators.bundle_creator[0]
        if first_creator_data.creator_name_identifier:
            # Prioritize ORCID/ISNI, then first available
            found_id = False
            for identifier in first_creator_data.creator_name_identifier:
                id_val = getattr(identifier, 'value', '')
                id_type_enum = getattr(identifier, 'identifier_type', None)

                if id_type_enum == CreatorNameIdentifierIdentifierType.ORCID:
                    primary_identifier = id_val
                    primary_identifier_type = PersonIdentifierTypeChoices.ORCID.value
                    found_id = True
                    break
                elif id_type_enum == CreatorNameIdentifierIdentifierType.ISNI:
                    primary_identifier = id_val
                    primary_identifier_type = PersonIdentifierTypeChoices.ISNI.value
                    found_id = True
                    break
            # If no ORCID/ISNI, take the first one if it exists
            if not found_id and first_creator_data.creator_name_identifier:
                identifier = first_creator_data.creator_name_identifier[0]
                primary_identifier = getattr(identifier, 'value', '')
                id_type_enum = getattr(identifier, 'identifier_type', None)
                primary_identifier_type = _map_person_identifier_type(id_type_enum)

    bundle_pub_info = BundlePublicationInfo.objects.filter(bundle=bundle).first()
    try:
        if bundle_pub_info:
            bundle_pub_info.publication_year = pub_year
            bundle_pub_info.data_provider = data_provider
            bundle_pub_info.identifier = primary_identifier
            bundle_pub_info.identifier_type = primary_identifier_type
            bundle_pub_info.save()
        else:
            bundle_pub_info = BundlePublicationInfo.objects.create(
                publication_year=pub_year,
                data_provider=data_provider,
                identifier=primary_identifier,  # Use extracted or empty string
                identifier_type=primary_identifier_type,  # Use extracted or empty/default string
                bundle=bundle,  # Set the bundle directly
            )
    except Exception as e:
        logger.error("Failed to create or update BundlePublicationInfo", extra={"error": e}, exc_info=True)
        return None # Or re-raise error

    # Reset related objects to keep updates idempotent
    bundle_pub_info.creators.clear()
    bundle_pub_info.contributors.clear()

    # Import creators (linking to the new bundle_pub_info)
    if hasattr(pub_info, 'bundle_creators') and pub_info.bundle_creators:
        import_creators(bundle_pub_info, pub_info.bundle_creators.bundle_creator)
        
    # Import contributors (linking to the new bundle_pub_info)
    if hasattr(pub_info, 'bundle_contributors') and pub_info.bundle_contributors:
        import_contributors(bundle_pub_info, pub_info.bundle_contributors.bundle_contributor)
    
    return bundle_pub_info


def _map_person_identifier_type(identifier_enum) -> str:
    if identifier_enum == CreatorNameIdentifierIdentifierType.ORCID:
        return PersonIdentifierTypeChoices.ORCID.value
    if identifier_enum == CreatorNameIdentifierIdentifierType.ISNI:
        return PersonIdentifierTypeChoices.ISNI.value
    if identifier_enum == CreatorNameIdentifierIdentifierType.EMAIL:
        return PersonIdentifierTypeChoices.EMAIL.value
    return PersonIdentifierTypeChoices.OTHER.value


def import_creators(bundle_pub_info: BundlePublicationInfo, creators_data: List) -> None:
    """
    Import creators from CMD data to Django models.
    
    Args:
        bundle_pub_info: The BundlePublicationInfo object to link creators to
        creators_data: List of creator data from the CMD object
    """
    for idx, creator_data in enumerate(creators_data):
        if not creator_data.creator_name:
            continue

        # Get or create creator using family_name and given_name as unique identifiers
        creator, created = BundleCreator.objects.get_or_create(
            family_name=creator_data.creator_name.creator_family_name,
            given_name=creator_data.creator_name.creator_given_name or "",
            defaults={
                'affiliation': None,
            }
        )
        
        # Handle identifiers
        if creator_data.creator_name_identifier:
            for identifier in creator_data.creator_name_identifier:
                # First check for specific identifier types
                creator.name_identifier = getattr(identifier, "value", "")
                creator.name_identifier_type = _map_person_identifier_type(
                    getattr(identifier, "identifier_type", None)
                )
                break
        
        # Handle affiliation
        if creator_data.creator_affiliation:
            creator.affiliation = creator_data.creator_affiliation[0]

        creator.save()
        BundlePublicationInfoCreator.objects.create(
            bundlepublicationinfo=bundle_pub_info,
            bundlecreator=creator,
            order=idx,
        )


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
                contributor.name_identifier = getattr(identifier, "value", "")
                id_type_enum = getattr(identifier, "identifier_type", None)
                if id_type_enum == ContributorNameIdentifierIdentifierType.ORCID:
                    contributor.name_identifier_type = PersonIdentifierTypeChoices.ORCID.value
                elif id_type_enum == ContributorNameIdentifierIdentifierType.ISNI:
                    contributor.name_identifier_type = PersonIdentifierTypeChoices.ISNI.value
                elif id_type_enum == ContributorNameIdentifierIdentifierType.EMAIL:
                    contributor.name_identifier_type = PersonIdentifierTypeChoices.EMAIL.value
                else:
                    contributor.name_identifier_type = PersonIdentifierTypeChoices.OTHER.value
                break
        
        # Handle affiliation
        if contributor_data.contributor_affiliation:
            contributor.affiliation = contributor_data.contributor_affiliation[0]
                
        # Handle role
        if contributor_data.contributor_role:
            contributor.role = contributor_data.contributor_role[0]
                
        contributor.save()
        bundle_pub_info.contributors.add(contributor)
