from dataclasses import asdict
from typing import Any
from django.db import transaction
from django.core.exceptions import ValidationError

# Update imports to use only the models we actually need
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo, BundleLocation, BundleKeyword, 
    BundleObjectLanguage, BundleObjectLanguageAlternativeName,
    BundleObjectLanguageTaxonomy, BundleObjectLanguageLanguageFamily
)
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_administrative_info import (
    BundleAdministrativeInfo, BundleLicense, BundleRightsHolder,
    BundleRightsHolderIdentifier
)
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleStructuralInfo, BundleAdditionalMetadataFile, BundleTopic,
    BundleTopics, BundleMembers, BundleHasBundleMember, 
    MediaResource, WrittenResource, WrittenResourceAnnotation, OtherResource
)
from lacos.blam.models.base_project_info import ProjectInfo, FunderInfo, FunderIdentifier
from lacos.blam.models.bundle.bundle_identifier import BundleIdentifier
from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd

class BundleImporter:
    """
    Handles importing BLAM XML into Django models.
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
            raise ValidationError(f"Invalid BLAM bundle XML: {str(e)}")
    
    @classmethod
    @transaction.atomic
    def import_from_xml(cls, xml_content: str) -> Bundle:
        """
        Imports XML content into Django models
        Returns the created Bundle instance
        """
        cmd_data = cls.validate_xml(xml_content)
        return cls._import_cmd_to_models(cmd_data)
    
    @classmethod
    def _import_cmd_to_models(cls, cmd_data: Cmd) -> Bundle:
        """
        Converts Cmd object to Django models
        """
        # Extract the main components from the CMD data
        bundle_repo = cmd_data.components.blam_bundle_repository_v10
        general_info = bundle_repo.bundle_general_info
        pub_info = bundle_repo.bundle_publication_info
        admin_info = bundle_repo.bundle_administrative_info
        structural_info = bundle_repo.bundle_structural_info

        # Create the main bundle with related models
        bundle = cls._create_bundle_with_related_models(
            general_info, pub_info, admin_info, structural_info, bundle_repo
        )
        
        # Import all related data
        cls._import_related_data(bundle, bundle_repo, general_info, pub_info, admin_info, structural_info)
        
        return bundle
    
    @classmethod
    def _create_bundle_with_related_models(cls, general_info, pub_info, admin_info, structural_info, bundle_repo):
        """Create the main bundle and its directly related models"""
        # Create BundleGeneralInfo - Contains basic descriptive information about the bundle
        bundle_general_info = BundleGeneralInfo.objects.create(
            bundle_version=general_info.bundle_version,
            display_title=general_info.bundle_display_title,
            description=general_info.bundle_description,
            recording_date=str(general_info.bundle_recording_date) if general_info.bundle_recording_date else None,
        )
        
        # Create BundlePublicationInfo - Contains information about publication and creators
        bundle_publication_info = BundlePublicationInfo.objects.create(
            publication_year=pub_info.bundle_publication_year.year if pub_info.bundle_publication_year else None,
            data_provider=pub_info.bundle_data_provider,
        )
        
        # Create BundleAdministrativeInfo - Contains access rights and administrative metadata
        bundle_administrative_info = BundleAdministrativeInfo.objects.create(
            access=admin_info.access.value if admin_info.access else None,
            availability_date=admin_info.availability_date,
        )
        
        # Create BundleStructuralInfo - Contains information about the bundle's structure and resources
        bundle_structural_info = BundleStructuralInfo.objects.create()

        # Create the main Bundle object that ties everything together
        bundle = Bundle.objects.create(
            general_info=bundle_general_info,
            publication_info=bundle_publication_info,
            administrative_info=bundle_administrative_info,
            structural_info=bundle_structural_info,
            md_license=bundle_repo.md_license.value if bundle_repo.md_license else None,
            md_license_uri=bundle_repo.md_license.uri if bundle_repo.md_license else None,
        )
        
        return bundle
    
    @classmethod
    def _import_related_data(cls, bundle, bundle_repo, general_info, pub_info, admin_info, structural_info):
        """Import all related data for the bundle"""
        # GENERAL INFORMATION SECTION
        # ---------------------------
        # Import bundle identifiers (DOI, Handle, etc.)
        cls._import_bundle_identifiers(bundle, general_info)
        
        # Import keywords/tags for the bundle
        cls._import_keywords(bundle, general_info)
        
        # Import object languages (languages that are the subject of study)
        cls._import_object_languages(bundle, general_info)
        
        # Import geographic location information
        cls._import_location(bundle, general_info)
        
        # PUBLICATION INFORMATION SECTION
        # -------------------------------
        # Import creators (primary authors/creators of the bundle)
        cls._import_creators(bundle, pub_info)
        
        # Import contributors (secondary contributors to the bundle)
        cls._import_contributors(bundle, pub_info)
        
        # PROJECT INFORMATION SECTION
        # ---------------------------
        # Import projects and their associated funders
        if hasattr(bundle_repo, 'project_info'):
            cls._import_projects(bundle, bundle_repo.project_info)
        
        # ADMINISTRATIVE INFORMATION SECTION
        # ----------------------------------
        # Import licenses that apply to the bundle
        cls._import_licenses(bundle, admin_info)
        
        # Import rights holders for the bundle
        cls._import_rights_holders(bundle, admin_info)
        
        # STRUCTURAL INFORMATION SECTION
        # ------------------------------
        # Import collection membership
        if hasattr(structural_info, 'bundle_is_member_of_collection') and structural_info.bundle_is_member_of_collection:
            cls._handle_collection_membership(bundle, structural_info)
            
        # Import additional metadata files
        if hasattr(structural_info, 'bundle_additional_metadata_file'):
            cls._import_additional_metadata_files(bundle, structural_info)
            
        # Import resources (media, written, and other)
        if hasattr(structural_info, 'bundle_resources'):
            cls._import_resources(bundle, structural_info.bundle_resources)
        
        # DATA INFORMATION SECTION
        # -----------------------
        # Import data-specific information if available
        if hasattr(bundle_repo, 'bundle_data_info'):
            cls._import_data_info(bundle, bundle_repo.bundle_data_info)
    
    @classmethod
    def _import_bundle_identifiers(cls, bundle: Bundle, general_info: Any) -> None:
        """Import persistent identifiers for the bundle (DOI, Handle, etc.)"""
        if hasattr(general_info, 'bundle_id'):
            for bundle_id in general_info.bundle_id:
                BundleIdentifier.objects.create(
                    bundle=bundle,
                    value=bundle_id.value,  # The actual identifier value
                    identifier_type=bundle_id.identifier_type.value if bundle_id.identifier_type else None  # Type (DOI, Handle, etc.)
                )
    
    @classmethod
    def _import_keywords(cls, bundle: Bundle, general_info: Any) -> None:
        """Import keywords/tags for the bundle"""
        if hasattr(general_info, 'bundle_keywords') and general_info.bundle_keywords:
            for keyword in general_info.bundle_keywords.bundle_keyword:
                bundle_keyword = BundleKeyword.objects.create(
                    keyword=keyword  # The keyword text
                )
                bundle.general_info.bundle_keywords.add(bundle_keyword)
    
    @classmethod
    def _import_object_languages(cls, bundle: Bundle, general_info: Any) -> None:
        """Import object languages (languages that are the subject of study)"""
        if hasattr(general_info, 'bundle_object_languages') and general_info.bundle_object_languages:
            for lang in general_info.bundle_object_languages.bundle_object_language:
                # Create the main language object
                obj_lang = BundleObjectLanguage.objects.create(
                    bundle=bundle.general_info,
                    name=lang.object_language_name,  # Language name
                    code=lang.object_language_code.value if lang.object_language_code else None,  # ISO code
                )
                
                # Add alternative names if any
                if lang.object_language_alternative_name:
                    for alt_name in lang.object_language_alternative_name:
                        BundleObjectLanguageAlternativeName.objects.create(
                            object_language=obj_lang,
                            name=alt_name  # Alternative name for the language
                        )
                
                # Add language family information if any
                if lang.object_language_language_family:
                    for family in lang.object_language_language_family:
                        BundleObjectLanguageLanguageFamily.objects.create(
                            object_language=obj_lang,
                            name=family.language_family_name,  # Family name
                            code=family.language_family_code  # Family code
                        )
                
                # Add taxonomy information if any
                if lang.object_language_taxonomy:
                    BundleObjectLanguageTaxonomy.objects.create(
                        object_language=obj_lang,
                        taxonomy_name=lang.object_language_taxonomy.taxonomy_name,  # Taxonomy name
                        taxonomy_code=lang.object_language_taxonomy.taxonomy_code  # Taxonomy code
                    )
                
                # Add to bundle's object languages
                bundle.general_info.bundle_object_languages.add(obj_lang)
    
    @classmethod
    def _import_location(cls, bundle: Bundle, general_info: Any) -> None:
        """Import geographic location information for the bundle"""
        if hasattr(general_info, 'bundle_location') and general_info.bundle_location:
            loc = general_info.bundle_location
            geo_location = None
            if hasattr(loc, 'bundle_geo_location') and loc.bundle_geo_location:
                # Store coordinates directly as string
                geo_location = loc.bundle_geo_location
                
            # Create location record with hierarchical geographic information
            bundle_location = BundleLocation.objects.create(
                geo_location=geo_location,
                location_name=loc.bundle_location_name if hasattr(loc, 'bundle_location_name') else None,
                location_facet=loc.bundle_location_facet if hasattr(loc, 'bundle_location_facet') else None,
                region_name=loc.bundle_region_name if hasattr(loc, 'bundle_region_name') else None,
                region_facet=loc.bundle_region_facet if hasattr(loc, 'bundle_region_facet') else None,
                country_name=loc.bundle_country_name if hasattr(loc, 'bundle_country_name') else None,
                country_facet=loc.bundle_country_facet if hasattr(loc, 'bundle_country_facet') else None,
                country_code=loc.bundle_country_code.value if hasattr(loc, 'bundle_country_code') and loc.bundle_country_code else None
            )
            
            # Link location to the bundle's general info
            bundle.general_info.bundle_location = bundle_location
            bundle.general_info.save()
    
    @classmethod
    def _handle_collection_membership(cls, bundle: Bundle, structural_info: Any) -> None:
        """Handle collection membership for the bundle"""
        # Check if this bundle belongs to a collection and link it appropriately
        if hasattr(structural_info, 'bundle_is_member_of_collection') and structural_info.bundle_is_member_of_collection:
            collection_id = structural_info.bundle_is_member_of_collection.value
            collection_type = structural_info.bundle_is_member_of_collection.identifier_type.value if structural_info.bundle_is_member_of_collection.identifier_type else None
            
            # Find the collection by its identifier
            try:
                # Update to use the correct model for collection identifiers
                from lacos.blam.models.collection.collection_repository import Collection
                from lacos.blam.models.collection.collection_identifier import CollectionIdentifier
                
                collection_identifier = CollectionIdentifier.objects.get(
                    value=collection_id,
                    identifier_type=collection_type
                )
                # Update the bundle's structural info with collection reference
                bundle.structural_info.is_member_of_collection = collection_identifier.collection
                bundle.structural_info.save()
            except CollectionIdentifier.DoesNotExist:
                # Log a warning instead of raising an exception
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Collection with identifier '{collection_id}' of type '{collection_type}' not found. "
                    f"Bundle {bundle.id} will not be linked to a collection."
                )
    
    @classmethod
    def _import_additional_metadata_files(cls, bundle: Bundle, structural_info: Any) -> None:
        """Import additional metadata files for the bundle"""
        if hasattr(structural_info, 'bundle_additional_metadata_file'):
            for metadata_file in structural_info.bundle_additional_metadata_file:
                file = BundleAdditionalMetadataFile.objects.create(
                    file_name=metadata_file.file_name,
                    file_pid=metadata_file.file_pid,
                    mime_type=metadata_file.mime_type,
                    is_metadata_for=metadata_file.is_metadata_for,
                    file_description=metadata_file.file_description if hasattr(metadata_file, 'file_description') else None
                )
                bundle.structural_info.additional_metadata_files.add(file)
    
    @classmethod
    def _import_resources(cls, bundle: Bundle, resources: Any) -> None:
        """Import all resources (media, written, and other) for the bundle"""
        # Create BundleResources container
        bundle_resources = BundleMembers.objects.create(bundle=bundle)
        
        # Import the three main types of resources
        if hasattr(resources, 'media_resource'):
            cls._import_media_resources(bundle, bundle_resources, resources)
        
        if hasattr(resources, 'written_resource'):
            cls._import_written_resources(bundle, bundle_resources, resources)
        
        if hasattr(resources, 'other_resource'):
            cls._import_other_resources(bundle, bundle_resources, resources)
    
    @classmethod
    def _import_media_resources(cls, bundle: Bundle, bundle_members: BundleMembers, resources: Any) -> None:
        """Import media resources (audio, video, images) for the bundle"""
        if resources.media_resource:
            for media in resources.media_resource:
                media_resource = MediaResource.objects.create(
                    file_name=media.file_name,
                    file_pid=media.file_pid,
                    mime_type=media.mime_type,
                    file_description=media.file_description if hasattr(media, 'file_description') else None,
                    file_length=media.file_length
                )
                
                # Create reference in BundleHasBundleMember
                BundleHasBundleMember.objects.create(
                    bundle_members=bundle_members,
                    member_uri=media.file_pid,
                    identifier_type="PID"  # Assuming PID is a valid choice
                )
    
    @classmethod
    def _import_written_resources(cls, bundle: Bundle, bundle_members: BundleMembers, resources: Any) -> None:
        """Import written resources (transcripts, annotations, texts) for the bundle"""
        if resources.written_resource:
            for written in resources.written_resource:
                written_resource = WrittenResource.objects.create(
                    file_name=written.file_name,
                    file_pid=written.file_pid,
                    mime_type=written.mime_type,
                    file_description=written.file_description if hasattr(written, 'file_description') else None
                )
                
                # Link annotations to their media resources
                if hasattr(written, 'is_annotation_of') and written.is_annotation_of:
                    for annotation_ref in written.is_annotation_of:
                        WrittenResourceAnnotation.objects.create(
                            written_resource=written_resource,
                            is_annotation_of=annotation_ref
                        )
                
                # Create reference in BundleHasBundleMember
                BundleHasBundleMember.objects.create(
                    bundle_members=bundle_members,
                    member_uri=written.file_pid,
                    identifier_type="PID"  # Assuming PID is a valid choice
                )
    
    @classmethod
    def _import_other_resources(cls, bundle: Bundle, bundle_members: BundleMembers, resources: Any) -> None:
        """Import other resources (documentation, metadata, etc.) for the bundle"""
        if resources.other_resource:
            for other in resources.other_resource:
                other_resource = OtherResource.objects.create(
                    file_name=other.file_name,
                    file_pid=other.file_pid,
                    mime_type=other.mime_type,
                    file_description=other.file_description if hasattr(other, 'file_description') else None
                )
                
                # Create reference in BundleHasBundleMember
                BundleHasBundleMember.objects.create(
                    bundle_members=bundle_members,
                    member_uri=other.file_pid,
                    identifier_type="PID"  # Assuming PID is a valid choice
                )

    @classmethod
    def _import_creators(cls, bundle: Bundle, pub_info: Any) -> None:
        """Import primary creators/authors of the bundle"""
        from lacos.blam.models.bundle.bundle_publication_info import BundleCreator, BundleCreatorName
        
        for creator in pub_info.bundle_creators.bundle_creator:
            # Create creator name
            creator_name = BundleCreatorName.objects.create(
                family_name=creator.creator_name.creator_family_name,  # Last name
                given_name=creator.creator_name.creator_given_name,  # First name
            )
            
            # Create creator
            creator_obj = BundleCreator.objects.create(
                name=creator_name,
                order=creator.order  # Order of appearance in citation
            )
            
            # Add name identifier if available
            if creator.creator_name_identifier:
                from lacos.blam.models.bundle.bundle_publication_info import BundleCreatorNameIdentifier
                
                BundleCreatorNameIdentifier.objects.create(
                    creator=creator_obj,
                    value=creator.creator_name_identifier[0].value,  # ORCID, etc.
                    identifier_type=creator.creator_name_identifier[0].identifier_type.value  # Type of ID
                )
            
            # Add affiliation if available
            if creator.creator_affiliation:
                creator_obj.affiliation = creator.creator_affiliation[0]  # Institutional affiliation
                creator_obj.save()
            
            # Add to the bundle's publication info
            bundle.publication_info.creators.add(creator_obj)

    @classmethod
    def _import_contributors(cls, bundle: Bundle, pub_info: Any) -> None:
        """Import secondary contributors to the bundle (editors, consultants, etc.)"""
        if pub_info.bundle_contributors:
            from lacos.blam.models.bundle.bundle_publication_info import BundleContributor, BundleContributorName
            
            for contributor in pub_info.bundle_contributors.bundle_contributor:
                # Create contributor name
                contributor_name = BundleContributorName.objects.create(
                    family_name=contributor.contributor_name.contributor_family_name,  # Last name
                    given_name=contributor.contributor_name.contributor_given_name  # First name
                )
                
                # Create contributor
                contributor_obj = BundleContributor.objects.create(
                    name=contributor_name,
                    role=contributor.contributor_role[0] if contributor.contributor_role else None  # Role (editor, consultant, etc.)
                )
                
                # Add name identifier if available
                if contributor.contributor_name_identifier:
                    from lacos.blam.models.bundle.bundle_publication_info import BundleContributorNameIdentifier
                    
                    BundleContributorNameIdentifier.objects.create(
                        contributor=contributor_obj,
                        value=contributor.contributor_name_identifier[0].value,  # ORCID, etc.
                        identifier_type=contributor.contributor_name_identifier[0].identifier_type.value  # Type of ID
                    )
                
                # Add affiliation if available
                if contributor.contributor_affiliation:
                    contributor_obj.affiliation = contributor.contributor_affiliation[0]  # Institutional affiliation
                    contributor_obj.save()
                
                # Add to the bundle's publication info
                bundle.publication_info.contributors.add(contributor_obj)

    @classmethod
    def _import_projects(cls, bundle: Bundle, project_info: Any) -> None:
        """Import projects and their associated funders"""
        if project_info and project_info.project:
            for proj in project_info.project:
                # Create the project record
                project = ProjectInfo.objects.create(
                    project_display_name=proj.project_display_name,  # Project name
                    project_description=proj.project_description  # Project description
                )
                
                # Import funders associated with this project
                if hasattr(proj, 'funder_infos') and proj.funder_infos:
                    for funder_info in proj.funder_infos.funder_info:
                        # Create funder info
                        funder = FunderInfo.objects.create(
                            funder_name=funder_info.funder_name,  # Funding organization name
                            grant_identifier=funder_info.grant_identifier,  # Grant/award number
                            grant_uri=funder_info.grant_uri  # URI for grant information
                        )
                        
                        # Add funder identifier if available
                        if funder_info.funder_identifier:
                            funder_identifier = FunderIdentifier.objects.create(
                                value=funder_info.funder_identifier.value,  # Funder ID
                                identifier_type=funder_info.funder_identifier.identifier_type.value  # Type of ID
                            )
                            # Link funder identifier to funder info
                            funder.funder_identifier = funder_identifier
                            funder.save()
                        
                        # Add to project's many-to-many relationship
                        project.funder_infos.add(funder)
                
                # Link project to bundle
                bundle.project_info = project
                bundle.save()

    @classmethod
    def _import_licenses(cls, bundle: Bundle, admin_info: Any) -> None:
        """Import licenses that apply to the bundle content"""
        for license in admin_info.license:
            license_obj = BundleLicense.objects.create(
                name=license.license_name,  # License name (e.g., "CC BY 4.0")
                identifier=license.license_identifier  # License URI or identifier
            )
            # Add to the bundle's administrative info
            bundle.administrative_info.licenses.add(license_obj)

    @classmethod
    def _import_rights_holders(cls, bundle: Bundle, admin_info: Any) -> None:
        """Import rights holders for the bundle content"""
        for holder in admin_info.rights_holder:
            rights_holder = BundleRightsHolder.objects.create(
                name=holder.rights_holder_name,  # Name of rights holder
            )
            
            # Add rights holder identifier if available
            if holder.rights_holder_identifier:
                identifier = BundleRightsHolderIdentifier.objects.create(
                    value=holder.rights_holder_identifier[0].value,  # Rights holder ID
                    identifier_type=holder.rights_holder_identifier[0].identifier_type.value  # Type of ID
                )
                # Link identifier to rights holder
                rights_holder.rights_holder_identifiers.add(identifier)
            
            # Add to the bundle's administrative info
            bundle.administrative_info.rights_holders.add(rights_holder)

    @classmethod
    def _import_data_info(cls, bundle: Bundle, data_info: Any) -> None:
        """Import data-specific information for the bundle"""
        # Import the three main types of data information
        cls._import_segmentation_units(bundle, data_info)
        cls._import_transcription_types(bundle, data_info)
        cls._import_translation_languages(bundle, data_info)
    
    @classmethod
    def _import_segmentation_units(cls, bundle: Bundle, data_info: Any) -> None:
        """Import segmentation units used in the bundle (e.g., utterance, word, morpheme)"""
        if hasattr(data_info, 'segmentation_units') and data_info.segmentation_units:
            from lacos.blam.models.bundle.bundle_data_info import BundleSegmentationUnit
            
            for unit in data_info.segmentation_units.segmentation_unit:
                BundleSegmentationUnit.objects.create(
                    bundle=bundle,
                    unit=unit  # Type of segmentation unit
                )
    
    @classmethod
    def _import_transcription_types(cls, bundle: Bundle, data_info: Any) -> None:
        """Import transcription types used in the bundle (e.g., phonetic, phonemic, orthographic)"""
        if hasattr(data_info, 'transcription_types') and data_info.transcription_types:
            from lacos.blam.models.bundle.bundle_data_info import BundleTranscriptionType
            
            for ttype in data_info.transcription_types.transcription_type:
                BundleTranscriptionType.objects.create(
                    bundle=bundle,
                    type=ttype  # Type of transcription
                )
    
    @classmethod
    def _import_translation_languages(cls, bundle: Bundle, data_info: Any) -> None:
        """Import languages used for translations in the bundle"""
        if hasattr(data_info, 'translation_languages') and data_info.translation_languages:
            from lacos.blam.models.bundle.bundle_data_info import BundleTranslationLanguage
            
            for tlang in data_info.translation_languages.translation_language:
                BundleTranslationLanguage.objects.create(
                    bundle=bundle,
                    name=tlang.translation_language_name,  # Language name
                    code=tlang.translation_language_code  # ISO language code
                )
