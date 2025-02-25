from dataclasses import asdict
from typing import Optional, List, Dict, Any
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.gis.geos import Point

from lacos.blam.models.collection import (
    BLAMCollection, CollectionObjectLanguage, LanguageAlternativeName,
    CollectionLocation, CollectionPublicationInfo, Creator, Contributor,
    CollectionAdministrativeInfo, License, RightsHolder, CollectionMember
)
from lacos.blam.blam_schemas.collection.blam_collection_repository_v1_0 import Cmd


class CollectionImporter:
    """
    Handles importing BLAM Collection XML into Django models.
    """
    
    @staticmethod
    def validate_xml(xml_content: str) -> Cmd:
        """
        Validates XML against schema and parses into dataclass
        Returns parsed Cmd object if valid, raises ValidationError if invalid
        """
        try:
            # Using the generated dataclasses to parse XML
            cmd_data = Cmd.from_xml(xml_content)
            return cmd_data
        except Exception as e:
            raise ValidationError(f"Invalid BLAM collection XML: {str(e)}")
    
    @classmethod
    @transaction.atomic
    def import_from_xml(cls, xml_content: str) -> BLAMCollection:
        """
        Imports XML content into Django models
        Returns the created BLAMCollection instance
        """
        cmd_data = cls.validate_xml(xml_content)
        return cls._import_cmd_to_models(cmd_data)
    
    @classmethod
    def _import_cmd_to_models(cls, cmd_data: Cmd) -> BLAMCollection:
        """
        Converts Cmd object to Django models
        """
        collection_repo = cmd_data.components.blam_collection_repository_v10
        general_info = collection_repo.collection_general_info
        pub_info = collection_repo.collection_publication_info
        admin_info = collection_repo.collection_administrative_info
        structural_info = collection_repo.collection_structural_info

        # Create main collection
        collection = BLAMCollection.objects.create(
            display_title=general_info.collection_display_title,
            version=general_info.collection_version,
            description=general_info.collection_description
        )

        # Import object languages
        cls._import_object_languages(collection, general_info)
        
        # Import locations
        cls._import_locations(collection, general_info)
        
        # Import publication info
        cls._import_publication_info(collection, pub_info)
        
        # Import administrative info
        cls._import_administrative_info(collection, admin_info)
        
        # Import collection members
        cls._import_collection_members(collection, structural_info)

        return collection
    
    @classmethod
    def _import_object_languages(cls, collection: BLAMCollection, general_info: Any) -> None:
        """Import object languages from XML to Django models"""
        if hasattr(general_info, 'collection_object_languages') and general_info.collection_object_languages:
            for lang_data in general_info.collection_object_languages.collection_object_language:
                # Create language object
                language = CollectionObjectLanguage.objects.create(
                    collection=collection,
                    name=lang_data.object_language_name,
                    display_name=lang_data.object_language_display_name,
                    iso_code=lang_data.object_language_iso639_3_code,
                    glottolog_code=lang_data.object_language_glottolog_code,
                    language_family=lang_data.object_language_taxonomy.object_language_language_family[0] 
                        if hasattr(lang_data, 'object_language_taxonomy') and 
                           lang_data.object_language_taxonomy and 
                           lang_data.object_language_taxonomy.object_language_language_family 
                        else None
                )
                
                # Import alternative names if any
                if hasattr(lang_data, 'object_language_alternative_names') and lang_data.object_language_alternative_names:
                    for alt_name in lang_data.object_language_alternative_names.object_language_alternative_name:
                        LanguageAlternativeName.objects.create(
                            language=language,
                            name=alt_name
                        )
    
    @classmethod
    def _import_locations(cls, collection: BLAMCollection, general_info: Any) -> None:
        """Import locations from XML to Django models"""
        if hasattr(general_info, 'collection_location') and general_info.collection_location:
            loc_data = general_info.collection_location
            
            # Create location object
            CollectionLocation.objects.create(
                collection=collection,
                geo_coordinates=loc_data.collection_geo_location if hasattr(loc_data, 'collection_geo_location') else None,
                location_name=loc_data.collection_location_name,
                location_facet=loc_data.collection_location_facet if hasattr(loc_data, 'collection_location_facet') else None,
                region_name=loc_data.collection_region_name if hasattr(loc_data, 'collection_region_name') else None,
                region_facet=loc_data.collection_region_facet if hasattr(loc_data, 'collection_region_facet') else None,
                country_name=loc_data.collection_country_name,
                country_facet=loc_data.collection_country_facet if hasattr(loc_data, 'collection_country_facet') else None,
                country_code=loc_data.collection_country_code
            )
    
    @classmethod
    def _import_publication_info(cls, collection: BLAMCollection, pub_info: Any) -> None:
        """Import publication info from XML to Django models"""
        # Create publication info
        publication_info = CollectionPublicationInfo.objects.create(
            collection=collection,
            publication_year=pub_info.collection_publication_year.year,
            data_provider=pub_info.collection_data_provider
        )
        
        # Import creators
        if hasattr(pub_info, 'collection_creators') and pub_info.collection_creators:
            for creator_data in pub_info.collection_creators.collection_creator:
                creator = Creator.objects.create(
                    publication_info=publication_info,
                    family_name=creator_data.creator_name.creator_family_name,
                    given_name=creator_data.creator_name.creator_given_name if hasattr(creator_data.creator_name, 'creator_given_name') else ""
                )
                
                # Add name identifier if exists
                if hasattr(creator_data, 'creator_name_identifier') and creator_data.creator_name_identifier:
                    creator.name_identifier = creator_data.creator_name_identifier[0].value
                    creator.save()
                
                # Add affiliation if exists
                if hasattr(creator_data, 'creator_affiliation') and creator_data.creator_affiliation:
                    creator.affiliation = creator_data.creator_affiliation[0]
                    creator.save()
        
        # Import contributors
        if hasattr(pub_info, 'collection_contributors') and pub_info.collection_contributors:
            for contributor_data in pub_info.collection_contributors.collection_contributor:
                contributor = Contributor.objects.create(
                    publication_info=publication_info,
                    family_name=contributor_data.contributor_name.contributor_family_name,
                    given_name=contributor_data.contributor_name.contributor_given_name if hasattr(contributor_data.contributor_name, 'contributor_given_name') else "",
                    role=contributor_data.contributor_role[0] if hasattr(contributor_data, 'contributor_role') and contributor_data.contributor_role else ""
                )
                
                # Add name identifier if exists
                if hasattr(contributor_data, 'contributor_name_identifier') and contributor_data.contributor_name_identifier:
                    contributor.name_identifier = contributor_data.contributor_name_identifier[0].value
                    contributor.save()
                
                # Add affiliation if exists
                if hasattr(contributor_data, 'contributor_affiliation') and contributor_data.contributor_affiliation:
                    contributor.affiliation = contributor_data.contributor_affiliation[0]
                    contributor.save()
    
    @classmethod
    def _import_administrative_info(cls, collection: BLAMCollection, admin_info: Any) -> None:
        """Import administrative info from XML to Django models"""
        # Create administrative info
        administrative_info = CollectionAdministrativeInfo.objects.create(
            collection=collection,
            access_type=admin_info.access.value,
            availability_date=admin_info.availability_date
        )
        
        # Import licenses
        if hasattr(admin_info, 'licenses') and admin_info.licenses:
            for license_data in admin_info.licenses.license:
                License.objects.create(
                    administrative_info=administrative_info,
                    name=license_data.value,
                    identifier=license_data.uri if hasattr(license_data, 'uri') else ""
                )
        
        # Import rights holders
        if hasattr(admin_info, 'rights_holders') and admin_info.rights_holders:
            for holder_data in admin_info.rights_holders.rights_holder:
                rights_holder = RightsHolder.objects.create(
                    administrative_info=administrative_info,
                    name=holder_data.value
                )
                
                # Add identifier if exists
                if hasattr(holder_data, 'identifier') and holder_data.identifier:
                    rights_holder.identifier = holder_data.identifier
                    rights_holder.identifier_type = holder_data.identifier_type.value if hasattr(holder_data, 'identifier_type') else None
                    rights_holder.save()
    
    @classmethod
    def _import_collection_members(cls, collection: BLAMCollection, structural_info: Any) -> None:
        """Import collection members from XML to Django models"""
        if hasattr(structural_info, 'collection_members') and structural_info.collection_members:
            for member_data in structural_info.collection_members.collection_has_collection_member:
                CollectionMember.objects.create(
                    collection=collection,
                    identifier=member_data.value,
                    identifier_type=member_data.identifier_type.value if hasattr(member_data, 'identifier_type') else ""
                )


# Simplified interface function
def import_collection_from_xml(xml_content: str) -> BLAMCollection:
    """Import a collection from XML content"""
    return CollectionImporter.import_from_xml(xml_content)
