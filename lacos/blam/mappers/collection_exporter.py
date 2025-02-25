from typing import Any, List, Optional
from django.contrib.gis.geos import Point

from lacos.blam.models.collection import (
    BLAMCollection, CollectionObjectLanguage, LanguageAlternativeName,
    CollectionLocation, CollectionPublicationInfo, Creator, Contributor,
    CollectionAdministrativeInfo, License, RightsHolder, CollectionMember
)
from lacos.blam.blam_schemas.collection.blam_collection_repository_v1_0 import (
    Cmd, CollectionIdIdentifierType, CollectionHasCollectionMemberIdentifierType,
    CreatorNameIdentifierIdentifierType, ContributorNameIdentifierIdentifierType,
    RightsHolderIdentifierIdentifierType
)
from xsdata.models.datatype import XmlDate


class CollectionExporter:
    """
    Handles exporting Django models to BLAM Collection XML.
    """
    
    @classmethod
    def export_to_xml(cls, collection: BLAMCollection) -> str:
        """
        Exports Django models to XML
        Returns XML string representation
        """
        cmd_data = cls._export_models_to_cmd(collection)
        return cmd_data.to_xml()
    
    @classmethod
    def _export_models_to_cmd(cls, collection: BLAMCollection) -> Cmd:
        """
        Converts Django models to Cmd object
        """
        # Create a new Cmd object
        cmd = Cmd()
        
        # Set up the basic structure
        cmd.header = Cmd.Header()
        cmd.resources = Cmd.Resources()
        cmd.components = Cmd.Components()
        
        # Create the BLAM collection repository component
        repo = Cmd.Components.BlamCollectionRepositoryV10()
        cmd.components.blam_collection_repository_v10 = repo
        
        # Set up the main sections
        repo.collection_general_info = cls._export_general_info(collection)
        repo.collection_publication_info = cls._export_publication_info(collection)
        repo.collection_administrative_info = cls._export_administrative_info(collection)
        repo.collection_structural_info = cls._export_structural_info(collection)
        
        return cmd
    
    @classmethod
    def _export_general_info(cls, collection: BLAMCollection) -> Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo:
        """Export general info section"""
        general_info = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo()
        
        # Set basic fields
        general_info.collection_version = collection.version
        general_info.collection_display_title = collection.display_title
        general_info.collection_description = collection.description
        
        # Export object languages if any
        if collection.languages.exists():
            languages = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionObjectLanguages()
            
            for lang in collection.languages.all():
                lang_obj = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage()
                lang_obj.object_language_name = lang.name
                lang_obj.object_language_display_name = lang.display_name
                
                if lang.iso_code:
                    lang_obj.object_language_iso639_3_code = lang.iso_code
                
                if lang.glottolog_code:
                    lang_obj.object_language_glottolog_code = lang.glottolog_code
                
                # Add language family if exists
                if lang.language_family:
                    taxonomy = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage.ObjectLanguageTaxonomy()
                    taxonomy.object_language_language_family.append(lang.language_family)
                    lang_obj.object_language_taxonomy = taxonomy
                
                # Add alternative names if any
                if lang.alternative_names.exists():
                    alt_names = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage.ObjectLanguageAlternativeNames()
                    for alt_name in lang.alternative_names.all():
                        alt_names.object_language_alternative_name.append(alt_name.name)
                    lang_obj.object_language_alternative_names = alt_names
                
                languages.collection_object_language.append(lang_obj)
            
            general_info.collection_object_languages = languages
        
        # Export locations if any
        if collection.locations.exists():
            for loc in collection.locations.all():
                loc_obj = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionLocation()
                
                loc_obj.collection_location_name = loc.location_name
                loc_obj.collection_country_name = loc.country_name
                
                # Create country code object
                country_code = Cmd.ComplextypeCollectionCountryCode611()
                country_code.value = loc.country_code
                loc_obj.collection_country_code = country_code
                
                if loc.geo_coordinates:
                    loc_obj.collection_geo_location = loc.geo_coordinates
                
                if loc.location_facet:
                    loc_obj.collection_location_facet = loc.location_facet
                
                if loc.region_name:
                    loc_obj.collection_region_name = loc.region_name
                
                if loc.region_facet:
                    loc_obj.collection_region_facet = loc.region_facet
                
                if loc.country_facet:
                    loc_obj.collection_country_facet = loc.country_facet
                
                general_info.collection_location.append(loc_obj)
        
        return general_info
    
    @classmethod
    def _export_publication_info(cls, collection: BLAMCollection) -> Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo:
        """Export publication info section"""
        pub_info = Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo()
        
        # Get publication info from collection
        try:
            collection_pub_info = collection.publication_info
            
            # Set basic fields
            pub_year = XmlDate()
            pub_year.year = collection_pub_info.publication_year
            pub_info.collection_publication_year = pub_year
            pub_info.collection_data_provider = collection_pub_info.data_provider
            
            # Export creators if any
            if collection_pub_info.creators.exists():
                creators = Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo.CollectionCreators()
                
                for creator in collection_pub_info.creators.all():
                    creator_obj = Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo.CollectionCreators.CollectionCreator()
                    
                    # Create creator name
                    name = Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo.CollectionCreators.CollectionCreator.CreatorName()
                    name.creator_family_name = creator.family_name
                    if creator.given_name:
                        name.creator_given_name = creator.given_name
                    creator_obj.creator_name = name
                    
                    # Add name identifier if exists
                    if creator.name_identifier:
                        id_obj = Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo.CollectionCreators.CollectionCreator.CreatorNameIdentifier()
                        id_obj.value = creator.name_identifier
                        creator_obj.creator_name_identifier.append(id_obj)
                    
                    # Add affiliation if exists
                    if creator.affiliation:
                        creator_obj.creator_affiliation.append(creator.affiliation)
                    
                    creators.collection_creator.append(creator_obj)
                
                pub_info.collection_creators = creators
            
            # Export contributors if any
            if collection_pub_info.contributors.exists():
                contributors = Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo.CollectionContributors()
                
                for contributor in collection_pub_info.contributors.all():
                    contributor_obj = Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo.CollectionContributors.CollectionContributor()
                    
                    # Create contributor name
                    name = Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo.CollectionContributors.CollectionContributor.ContributorName()
                    name.contributor_family_name = contributor.family_name
                    if contributor.given_name:
                        name.contributor_given_name = contributor.given_name
                    contributor_obj.contributor_name = name
                    
                    # Add name identifier if exists
                    if contributor.name_identifier:
                        id_obj = Cmd.Components.BlamCollectionRepositoryV10.CollectionPublicationInfo.CollectionContributors.CollectionContributor.ContributorNameIdentifier()
                        id_obj.value = contributor.name_identifier
                        contributor_obj.contributor_name_identifier.append(id_obj)
                    
                    # Add affiliation if exists
                    if contributor.affiliation:
                        contributor_obj.contributor_affiliation.append(contributor.affiliation)
                    
                    # Add role if exists
                    if contributor.role:
                        contributor_obj.contributor_role.append(contributor.role)
                    
                    contributors.collection_contributor.append(contributor_obj)
                
                pub_info.collection_contributors = contributors
        
        except CollectionPublicationInfo.DoesNotExist:
            # If no publication info exists, create minimal required fields
            pub_year = XmlDate()
            pub_year.year = 2023  # Default year
            pub_info.collection_publication_year = pub_year
            pub_info.collection_data_provider = "Unknown"
        
        return pub_info
    
    @classmethod
    def _export_administrative_info(cls, collection: BLAMCollection) -> Cmd.Components.BlamCollectionRepositoryV10.CollectionAdministrativeInfo:
        """Export administrative info section"""
        admin_info = Cmd.Components.BlamCollectionRepositoryV10.CollectionAdministrativeInfo()
        
        # Get administrative info from collection
        try:
            collection_admin_info = collection.administrative_info
            
            # Set basic fields
            admin_info.access = collection_admin_info.access_type
            admin_info.availability_date = collection_admin_info.availability_date
            
            # Export licenses if any
            if collection_admin_info.licenses.exists():
                licenses = Cmd.Components.BlamCollectionRepositoryV10.CollectionAdministrativeInfo.Licenses()
                
                for license in collection_admin_info.licenses.all():
                    license_obj = Cmd.Components.BlamCollectionRepositoryV10.CollectionAdministrativeInfo.Licenses.License()
                    license_obj.value = license.name
                    if license.identifier:
                        license_obj.uri = license.identifier
                    licenses.license.append(license_obj)
                
                admin_info.licenses = licenses
            
            # Export rights holders if any
            if collection_admin_info.rights_holders.exists():
                rights_holders = Cmd.Components.BlamCollectionRepositoryV10.CollectionAdministrativeInfo.RightsHolders()
                
                for holder in collection_admin_info.rights_holders.all():
                    holder_obj = Cmd.Components.BlamCollectionRepositoryV10.CollectionAdministrativeInfo.RightsHolders.RightsHolder()
                    holder_obj.value = holder.name
                    
                    if holder.identifier:
                        holder_obj.identifier = holder.identifier
                        if holder.identifier_type:
                            holder_obj.identifier_type = RightsHolderIdentifierIdentifierType(holder.identifier_type)
                    
                    rights_holders.rights_holder.append(holder_obj)
                
                admin_info.rights_holders = rights_holders
        
        except CollectionAdministrativeInfo.DoesNotExist:
            # If no administrative info exists, create minimal required fields
            admin_info.access = "open"
            admin_info.availability_date = XmlDate.now()
        
        return admin_info
    
    @classmethod
    def _export_structural_info(cls, collection: BLAMCollection) -> Cmd.Components.BlamCollectionRepositoryV10.CollectionStructuralInfo:
        """Export structural info section"""
        structural_info = Cmd.Components.BlamCollectionRepositoryV10.CollectionStructuralInfo()
        
        # Export collection members if any
        if collection.members.exists():
            members = Cmd.Components.BlamCollectionRepositoryV10.CollectionStructuralInfo.CollectionMembers()
            
            for member in collection.members.all():
                member_obj = Cmd.Components.BlamCollectionRepositoryV10.CollectionStructuralInfo.CollectionMembers.CollectionHasCollectionMember()
                member_obj.value = member.identifier
                
                if member.identifier_type:
                    try:
                        member_obj.identifier_type = CollectionHasCollectionMemberIdentifierType(member.identifier_type)
                    except ValueError:
                        # If the identifier type is not valid, don't set it
                        pass
                
                members.collection_has_collection_member.append(member_obj)
            
            structural_info.collection_members = members
        
        return structural_info


# Simplified interface function
def export_collection_to_xml(collection: BLAMCollection) -> str:
    """Export a collection to XML content"""
    return CollectionExporter.export_to_xml(collection)
