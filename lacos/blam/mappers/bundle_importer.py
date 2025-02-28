from dataclasses import asdict
from typing import Any
from django.db import transaction
from django.core.exceptions import ValidationError

from lacos.blam.models.bundle import (
    BLAMBundle, BundleIdentifier, ObjectLanguage, 
    ObjectLanguageAlternativeName, BundleLocation,
    Creator, Contributor, License, RightsHolder,
    MediaResource, WrittenResource, OtherResource,
    BundleKeyword, Project, Funder, SegmentationUnit,
    TranscriptionType, TranslationLanguage,
    CollectionIdentifier
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
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
            recording_date=str(general_info.bundle_recording_date),
            is_member_of_collection=structural_info.bundle_is_member_of_collection.value,
            is_member_of_collection_type=structural_info.bundle_is_member_of_collection.identifier_type.value,
        )
        
        # Create BundlePublicationInfo - Contains information about publication and creators
        bundle_publication_info = BundlePublicationInfo.objects.create(
            publication_year=pub_info.bundle_publication_year.year,
            data_provider=pub_info.bundle_data_provider,
        )
        
        # Create BundleAdministrativeInfo - Contains access rights and administrative metadata
        bundle_administrative_info = BundleAdministrativeInfo.objects.create(
            access=admin_info.access.value,
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
            md_license=bundle_repo.md_license,
            md_license_uri=bundle_repo.md_license.uri,
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
        cls._import_projects(bundle, bundle_repo.project_info)
        
        # ADMINISTRATIVE INFORMATION SECTION
        # ----------------------------------
        # Import licenses that apply to the bundle
        cls._import_licenses(bundle, admin_info)
        
        # Import rights holders for the bundle
        cls._import_rights_holders(bundle, admin_info)
        
        # STRUCTURAL INFORMATION SECTION
        # ------------------------------
        # Import resources (media, written, and other)
        cls._import_resources(bundle, structural_info.bundle_resources)
        
        # DATA INFORMATION SECTION
        # -----------------------
        # Import data-specific information if available
        if hasattr(bundle_repo, 'bundle_data_info'):
            cls._import_data_info(bundle, bundle_repo.bundle_data_info)

        # COLLECTION MEMBERSHIP
        # --------------------
        # Handle collection membership for the bundle
        cls._handle_collection_membership(bundle, general_info)
    
    @classmethod
    def _handle_collection_membership(cls, bundle, general_info):
        """Handle collection membership for the bundle"""
        # Check if this bundle belongs to a collection and link it appropriately
        if hasattr(general_info, 'bundle_is_member_of_collection') and general_info.bundle_is_member_of_collection:
            collection_id = general_info.bundle_is_member_of_collection
            collection_type = general_info.bundle_is_member_of_collection_type
            
            # Find the collection by its identifier
            try:
                collection_identifier = CollectionIdentifier.objects.get(
                    value=collection_id,
                    identifier_type=collection_type
                )
                # Update the general_info with collection reference
                bundle.general_info.is_member_of_collection = collection_identifier.collection.id
                bundle.general_info.is_member_of_collection_type = collection_type
                bundle.general_info.save()
            except CollectionIdentifier.DoesNotExist:
                # Raise an exception with a clear error message
                raise ValueError(
                    f"Cannot import bundle: Collection with identifier '{collection_id}' of type '{collection_type}' "
                    f"not found. Collections must be created before their associated bundles."
                )

    @classmethod
    def _import_location(cls, bundle: Bundle, general_info: Any) -> None:
        """Import geographic location information for the bundle"""
        if general_info.bundle_location:
            loc = general_info.bundle_location
            geo_location = None
            if hasattr(loc, 'bundle_geo_location') and loc.bundle_geo_location:
                # Store coordinates directly as string (format: "latitude,longitude")
                geo_location = loc.bundle_geo_location
                    
            # Create location record with hierarchical geographic information
            BundleLocation.objects.create(
                bundle=bundle,
                geo_location=geo_location,
                location_name=loc.bundle_location_name,  # Specific location name
                location_facet=loc.bundle_location_facet,  # Location category
                region_name=loc.bundle_region_name,  # Region/state/province
                region_facet=loc.bundle_region_facet,  # Region category
                country_name=loc.bundle_country_name,  # Country name
                country_facet=loc.bundle_country_facet,  # Country category
                country_code=loc.bundle_country_code  # ISO country code
            )

    @classmethod
    def _import_bundle_identifiers(cls, bundle: Bundle, general_info: Any) -> None:
        """Import persistent identifiers for the bundle (DOI, Handle, etc.)"""
        for bundle_id in general_info.bundle_id:
            BundleIdentifier.objects.create(
                bundle=bundle,
                value=bundle_id.value,  # The actual identifier value
                identifier_type=bundle_id.identifier_type.value if bundle_id.identifier_type else None  # Type (DOI, Handle, etc.)
            )

    @classmethod
    def _import_keywords(cls, bundle: Bundle, general_info: Any) -> None:
        """Import subject keywords/tags for the bundle"""
        if hasattr(general_info, 'bundle_keywords') and general_info.bundle_keywords:
            for keyword in general_info.bundle_keywords.bundle_keyword:
                BundleKeyword.objects.create(
                    bundle=bundle,
                    keyword=keyword  # Individual keyword/tag
                )

    @classmethod
    def _import_object_languages(cls, bundle: Bundle, general_info: Any) -> None:
        """Import languages that are the subject of study in this bundle"""
        for lang in general_info.bundle_object_languages.bundle_object_language:
            # Create the main language record
            obj_lang = ObjectLanguage.objects.create(
                bundle=bundle,
                display_name=lang.object_language_display_name,  # Human-readable name
                name=lang.object_language_name,  # Standard name
                iso_639_3_code=lang.object_language_iso639_3_code,  # ISO 639-3 code
                glottolog_code=lang.object_language_glottolog_code,  # Glottolog code
                language_family=lang.object_language_taxonomy.object_language_language_family[0]  # Language family
            )
            
            # Import alternative names/variants of the language if any
            if lang.object_language_alternative_names:
                for alt_name in lang.object_language_alternative_names.object_language_alternative_name:
                    ObjectLanguageAlternativeName.objects.create(
                        language=obj_lang,
                        name=alt_name  # Alternative name for the language
                    )

    @classmethod
    def _import_creators(cls, bundle: Bundle, pub_info: Any) -> None:
        """Import primary creators/authors of the bundle"""
        for creator in pub_info.bundle_creators.bundle_creator:
            Creator.objects.create(
                bundle=bundle,
                name_identifier=creator.creator_name_identifier[0].value if creator.creator_name_identifier else None,  # ORCID, etc.
                name_identifier_type=creator.creator_name_identifier[0].identifier_type.value if creator.creator_name_identifier else None,  # Type of ID
                affiliation=creator.creator_affiliation[0] if creator.creator_affiliation else None,  # Institutional affiliation
                family_name=creator.creator_name.creator_family_name,  # Last name
                given_name=creator.creator_name.creator_given_name,  # First name
                order=creator.order  # Order of appearance in citation
            )

    @classmethod
    def _import_contributors(cls, bundle: Bundle, pub_info: Any) -> None:
        """Import secondary contributors to the bundle (editors, consultants, etc.)"""
        if pub_info.bundle_contributors:
            for contributor in pub_info.bundle_contributors.bundle_contributor:
                Contributor.objects.create(
                    bundle=bundle,
                    name_identifier=contributor.contributor_name_identifier[0].value if contributor.contributor_name_identifier else None,  # ORCID, etc.
                    name_identifier_type=contributor.contributor_name_identifier[0].identifier_type.value if contributor.contributor_name_identifier else None,  # Type of ID
                    affiliation=contributor.contributor_affiliation[0] if contributor.contributor_affiliation else None,  # Institutional affiliation
                    role=contributor.contributor_role[0],  # Role (editor, consultant, etc.)
                    family_name=contributor.contributor_name.contributor_family_name,  # Last name
                    given_name=contributor.contributor_name.contributor_given_name  # First name
                )

    @classmethod
    def _import_projects(cls, bundle: Bundle, project_info: Any) -> None:
        """Import projects and their associated funders"""
        if project_info and project_info.project:
            for proj in project_info.project:
                # Create the project record
                project = Project.objects.create(
                    bundle=bundle,
                    display_name=proj.project_display_name,  # Project name
                    description=proj.project_description  # Project description
                )
                
                # Import funders associated with this project
                if hasattr(proj, 'funder_infos') and proj.funder_infos:
                    for funder_info in proj.funder_infos.funder_info:
                        Funder.objects.create(
                            project=project,
                            name=funder_info.funder_name,  # Funding organization name
                            identifier=funder_info.funder_identifier.value if funder_info.funder_identifier else None,  # Funder ID
                            identifier_type=funder_info.funder_identifier.identifier_type.value if funder_info.funder_identifier else None,  # Type of ID
                            grant_identifier=funder_info.grant_identifier,  # Grant/award number
                            grant_uri=funder_info.grant_uri  # URI for grant information
                        )

    @classmethod
    def _import_licenses(cls, bundle: Bundle, admin_info: Any) -> None:
        """Import licenses that apply to the bundle content"""
        for license in admin_info.license:
            License.objects.create(
                bundle=bundle,
                name=license.license_name,  # License name (e.g., "CC BY 4.0")
                identifier=license.license_identifier  # License URI or identifier
            )

    @classmethod
    def _import_rights_holders(cls, bundle: Bundle, admin_info: Any) -> None:
        """Import rights holders for the bundle content"""
        for holder in admin_info.rights_holder:
            RightsHolder.objects.create(
                bundle=bundle,
                name=holder.rights_holder_name,  # Name of rights holder
                identifier=holder.rights_holder_identifier[0].value if holder.rights_holder_identifier else None,  # Rights holder ID
                identifier_type=holder.rights_holder_identifier[0].identifier_type.value if holder.rights_holder_identifier else None  # Type of ID
            )

    @classmethod
    def _import_resources(cls, bundle: Bundle, resources: Any) -> None:
        """Import all resources (media, written, and other) for the bundle"""
        # Import the three main types of resources
        cls._import_media_resources(bundle, resources)
        cls._import_written_resources(bundle, resources)
        cls._import_other_resources(bundle, resources)
    
    @classmethod
    def _import_media_resources(cls, bundle: Bundle, resources: Any) -> None:
        """Import media resources (audio, video, images) for the bundle"""
        if resources.media_resource:
            for media in resources.media_resource:
                MediaResource.objects.create(
                    bundle=bundle,
                    ref=media.ref[0] if media.ref else "",  # Reference ID for internal linking
                    file_name=media.file_name,  # Filename
                    file_pid=media.file_pid,  # Persistent identifier for the file
                    mime_type=media.mime_type,  # MIME type (e.g., audio/wav)
                    file_description=media.file_description,  # Description of the file
                    file_length=media.file_length  # Duration for audio/video
                )
    
    @classmethod
    def _import_written_resources(cls, bundle: Bundle, resources: Any) -> None:
        """Import written resources (transcripts, annotations, texts) for the bundle"""
        if resources.written_resource:
            for written in resources.written_resource:
                # Create the written resource
                wr = WrittenResource.objects.create(
                    bundle=bundle,
                    ref=written.ref[0] if written.ref else "",  # Reference ID for internal linking
                    file_name=written.file_name,  # Filename
                    file_pid=written.file_pid,  # Persistent identifier for the file
                    mime_type=written.mime_type,  # MIME type (e.g., text/xml)
                    file_description=written.file_description  # Description of the file
                )
                
                # Link annotations to their media resources
                if written.is_annotation_of:
                    for annotation_ref in written.is_annotation_of:
                        media = MediaResource.objects.filter(ref=annotation_ref, bundle=bundle).first()
                        if media:
                            wr.is_annotation_of.add(media)  # Create many-to-many relationship
    
    @classmethod
    def _import_other_resources(cls, bundle: Bundle, resources: Any) -> None:
        """Import other resources (documentation, metadata, etc.) for the bundle"""
        if resources.other_resource:
            for other in resources.other_resource:
                OtherResource.objects.create(
                    bundle=bundle,
                    ref=other.ref[0] if other.ref else "",  # Reference ID for internal linking
                    file_name=other.file_name,  # Filename
                    file_pid=other.file_pid,  # Persistent identifier for the file
                    mime_type=other.mime_type,  # MIME type
                    file_description=other.file_description  # Description of the file
                )

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
            for unit in data_info.segmentation_units.segmentation_unit:
                SegmentationUnit.objects.create(
                    bundle=bundle,
                    unit=unit  # Type of segmentation unit
                )
    
    @classmethod
    def _import_transcription_types(cls, bundle: Bundle, data_info: Any) -> None:
        """Import transcription types used in the bundle (e.g., phonetic, phonemic, orthographic)"""
        if hasattr(data_info, 'transcription_types') and data_info.transcription_types:
            for ttype in data_info.transcription_types.transcription_type:
                TranscriptionType.objects.create(
                    bundle=bundle,
                    type=ttype  # Type of transcription
                )
    
    @classmethod
    def _import_translation_languages(cls, bundle: Bundle, data_info: Any) -> None:
        """Import languages used for translations in the bundle"""
        if hasattr(data_info, 'translation_languages') and data_info.translation_languages:
            for tlang in data_info.translation_languages.translation_language:
                TranslationLanguage.objects.create(
                    bundle=bundle,
                    name=tlang.translation_language_name,  # Language name
                    code=tlang.translation_language_code  # ISO language code
                )

