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
    def import_from_xml(cls, xml_content: str) -> BLAMBundle:
        """
        Imports XML content into Django models
        Returns the created BLAMBundle instance
        """
        cmd_data = cls.validate_xml(xml_content)
        return cls._import_cmd_to_models(cmd_data)
    
    @classmethod
    def _import_cmd_to_models(cls, cmd_data: Cmd) -> BLAMBundle:
        """
        Converts Cmd object to Django models
        """
        bundle_repo = cmd_data.components.blam_bundle_repository_v10
        general_info = bundle_repo.bundle_general_info
        pub_info = bundle_repo.bundle_publication_info
        admin_info = bundle_repo.bundle_administrative_info
        structural_info = bundle_repo.bundle_structural_info

        # Create main bundle
        bundle = BLAMBundle.objects.create(
            bundle_version=general_info.bundle_version,
            bundle_display_title=general_info.bundle_display_title,
            bundle_description=general_info.bundle_description,
            bundle_recording_date=str(general_info.bundle_recording_date),
            bundle_publication_year=pub_info.bundle_publication_year.year,
            bundle_data_provider=pub_info.bundle_data_provider,
            access=admin_info.access.value,
            availability_date=admin_info.availability_date,
            bundle_is_member_of_collection=structural_info.bundle_is_member_of_collection.value,
            bundle_is_member_of_collection_type=structural_info.bundle_is_member_of_collection.identifier_type.value,
            md_license=bundle_repo.md_license,
            md_license_uri=bundle_repo.md_license.uri,
        )

        # Import bundle IDs
        cls._import_bundle_identifiers(bundle, general_info)
        
        # Import keywords if any
        cls._import_keywords(bundle, general_info)
        
        # Import object languages
        cls._import_object_languages(bundle, general_info)
        
        # Import location
        cls._import_location(bundle, general_info)
        
        # Import creators
        cls._import_creators(bundle, pub_info)
        
        # Import contributors
        cls._import_contributors(bundle, pub_info)
        
        # Import projects and funders
        cls._import_projects(bundle, bundle_repo.project_info)
        
        # Import licenses
        cls._import_licenses(bundle, admin_info)
        
        # Import rights holders
        cls._import_rights_holders(bundle, admin_info)
        
        # Import resources
        cls._import_resources(bundle, structural_info.bundle_resources)
        
        # Import data info (segmentation units, transcription types, translation languages)
        if hasattr(bundle_repo, 'bundle_data_info'):
            cls._import_data_info(bundle, bundle_repo.bundle_data_info)

        # Handle collection membership
        if hasattr(general_info, 'bundle_is_member_of_collection') and general_info.bundle_is_member_of_collection:
            collection_id = general_info.bundle_is_member_of_collection
            collection_type = general_info.bundle_is_member_of_collection_type
            
            # Find the collection by its identifier
            try:
                collection_identifier = CollectionIdentifier.objects.get(
                    value=collection_id,
                    identifier_type=collection_type
                )
                # Set the collection reference
                bundle.bundle_is_member_of_collection = collection_identifier.collection.id
                bundle.bundle_is_member_of_collection_type = collection_type
            except CollectionIdentifier.DoesNotExist:
                # Raise an exception with a clear error message
                raise ValueError(
                    f"Cannot import bundle: Collection with identifier '{collection_id}' of type '{collection_type}' "
                    f"not found. Collections must be created before their associated bundles."
                )
            
            bundle.save()

        return bundle
    
    @classmethod
    def _import_bundle_identifiers(cls, bundle: BLAMBundle, general_info: Any) -> None:
        for bundle_id in general_info.bundle_id:
            BundleIdentifier.objects.create(
                bundle=bundle,
                value=bundle_id.value,
                identifier_type=bundle_id.identifier_type.value if bundle_id.identifier_type else None
            )
    
    @classmethod
    def _import_keywords(cls, bundle: BLAMBundle, general_info: Any) -> None:
        if hasattr(general_info, 'bundle_keywords') and general_info.bundle_keywords:
            for keyword in general_info.bundle_keywords.bundle_keyword:
                BundleKeyword.objects.create(
                    bundle=bundle,
                    keyword=keyword
                )
    
    @classmethod
    def _import_object_languages(cls, bundle: BLAMBundle, general_info: Any) -> None:
        for lang in general_info.bundle_object_languages.bundle_object_language:
            obj_lang = ObjectLanguage.objects.create(
                bundle=bundle,
                display_name=lang.object_language_display_name,
                name=lang.object_language_name,
                iso_639_3_code=lang.object_language_iso639_3_code,
                glottolog_code=lang.object_language_glottolog_code,
                language_family=lang.object_language_taxonomy.object_language_language_family[0]
            )
            
            # Import alternative names if any
            if lang.object_language_alternative_names:
                for alt_name in lang.object_language_alternative_names.object_language_alternative_name:
                    ObjectLanguageAlternativeName.objects.create(
                        language=obj_lang,
                        name=alt_name
                    )
    
    @classmethod
    def _import_location(cls, bundle: BLAMBundle, general_info: Any) -> None:
        if general_info.bundle_location:
            loc = general_info.bundle_location
            geo_location = None
            if hasattr(loc, 'bundle_geo_location') and loc.bundle_geo_location:
                # Store coordinates directly as string instead of creating Point object
                geo_location = loc.bundle_geo_location
                    
            BundleLocation.objects.create(
                bundle=bundle,
                geo_location=geo_location,
                location_name=loc.bundle_location_name,
                location_facet=loc.bundle_location_facet,
                region_name=loc.bundle_region_name,
                region_facet=loc.bundle_region_facet,
                country_name=loc.bundle_country_name,
                country_facet=loc.bundle_country_facet,
                country_code=loc.bundle_country_code
            )
    
    @classmethod
    def _import_creators(cls, bundle: BLAMBundle, pub_info: Any) -> None:
        for creator in pub_info.bundle_creators.bundle_creator:
            Creator.objects.create(
                bundle=bundle,
                name_identifier=creator.creator_name_identifier[0].value if creator.creator_name_identifier else None,
                name_identifier_type=creator.creator_name_identifier[0].identifier_type.value if creator.creator_name_identifier else None,
                affiliation=creator.creator_affiliation[0] if creator.creator_affiliation else None,
                family_name=creator.creator_name.creator_family_name,
                given_name=creator.creator_name.creator_given_name,
                order=creator.order
            )
    
    @classmethod
    def _import_contributors(cls, bundle: BLAMBundle, pub_info: Any) -> None:
        if pub_info.bundle_contributors:
            for contributor in pub_info.bundle_contributors.bundle_contributor:
                Contributor.objects.create(
                    bundle=bundle,
                    name_identifier=contributor.contributor_name_identifier[0].value if contributor.contributor_name_identifier else None,
                    name_identifier_type=contributor.contributor_name_identifier[0].identifier_type.value if contributor.contributor_name_identifier else None,
                    affiliation=contributor.contributor_affiliation[0] if contributor.contributor_affiliation else None,
                    role=contributor.contributor_role[0],
                    family_name=contributor.contributor_name.contributor_family_name,
                    given_name=contributor.contributor_name.contributor_given_name
                )
    
    @classmethod
    def _import_projects(cls, bundle: BLAMBundle, project_info: Any) -> None:
        if project_info and project_info.project:
            for proj in project_info.project:
                project = Project.objects.create(
                    bundle=bundle,
                    display_name=proj.project_display_name,
                    description=proj.project_description
                )
                
                # Import funders if any
                if hasattr(proj, 'funder_infos') and proj.funder_infos:
                    for funder_info in proj.funder_infos.funder_info:
                        Funder.objects.create(
                            project=project,
                            name=funder_info.funder_name,
                            identifier=funder_info.funder_identifier.value if funder_info.funder_identifier else None,
                            identifier_type=funder_info.funder_identifier.identifier_type.value if funder_info.funder_identifier else None,
                            grant_identifier=funder_info.grant_identifier,
                            grant_uri=funder_info.grant_uri
                        )
    
    @classmethod
    def _import_licenses(cls, bundle: BLAMBundle, admin_info: Any) -> None:
        for license in admin_info.license:
            License.objects.create(
                bundle=bundle,
                name=license.license_name,
                identifier=license.license_identifier
            )
    
    @classmethod
    def _import_rights_holders(cls, bundle: BLAMBundle, admin_info: Any) -> None:
        for holder in admin_info.rights_holder:
            RightsHolder.objects.create(
                bundle=bundle,
                name=holder.rights_holder_name,
                identifier=holder.rights_holder_identifier[0].value if holder.rights_holder_identifier else None,
                identifier_type=holder.rights_holder_identifier[0].identifier_type.value if holder.rights_holder_identifier else None
            )
    
    @classmethod
    def _import_resources(cls, bundle: BLAMBundle, resources: Any) -> None:
        # Import media resources
        if resources.media_resource:
            for media in resources.media_resource:
                MediaResource.objects.create(
                    bundle=bundle,
                    ref=media.ref[0] if media.ref else "",
                    file_name=media.file_name,
                    file_pid=media.file_pid,
                    mime_type=media.mime_type,
                    file_description=media.file_description,
                    file_length=media.file_length
                )
        
        # Import written resources
        if resources.written_resource:
            for written in resources.written_resource:
                wr = WrittenResource.objects.create(
                    bundle=bundle,
                    ref=written.ref[0] if written.ref else "",
                    file_name=written.file_name,
                    file_pid=written.file_pid,
                    mime_type=written.mime_type,
                    file_description=written.file_description
                )
                
                # Add annotations if any
                if written.is_annotation_of:
                    for annotation_ref in written.is_annotation_of:
                        media = MediaResource.objects.filter(ref=annotation_ref, bundle=bundle).first()
                        if media:
                            wr.is_annotation_of.add(media)
        
        # Import other resources
        if resources.other_resource:
            for other in resources.other_resource:
                OtherResource.objects.create(
                    bundle=bundle,
                    ref=other.ref[0] if other.ref else "",
                    file_name=other.file_name,
                    file_pid=other.file_pid,
                    mime_type=other.mime_type,
                    file_description=other.file_description
                )
    
    @classmethod
    def _import_data_info(cls, bundle: BLAMBundle, data_info: Any) -> None:
        # Import segmentation units
        if hasattr(data_info, 'segmentation_units') and data_info.segmentation_units:
            for unit in data_info.segmentation_units.segmentation_unit:
                SegmentationUnit.objects.create(
                    bundle=bundle,
                    unit=unit
                )
        
        # Import transcription types
        if hasattr(data_info, 'transcription_types') and data_info.transcription_types:
            for ttype in data_info.transcription_types.transcription_type:
                TranscriptionType.objects.create(
                    bundle=bundle,
                    type=ttype
                )
        
        # Import translation languages
        if hasattr(data_info, 'translation_languages') and data_info.translation_languages:
            for tlang in data_info.translation_languages.translation_language:
                TranslationLanguage.objects.create(
                    bundle=bundle,
                    name=tlang.translation_language_name,
                    code=tlang.translation_language_code
                )


class BundleExporter:
    """
    Handles exporting Django models to BLAM XML.
    """
    
    @classmethod
    def export_to_xml(cls, bundle: BLAMBundle) -> str:
        """
        Exports Django models to XML
        Returns XML string representation
        """
        cmd_data = cls._export_models_to_cmd(bundle)
        return cmd_data.to_xml()
    
    @classmethod
    def _export_models_to_cmd(cls, bundle: BLAMBundle) -> Cmd:
        """
        Converts Django models to Cmd object
        """
        # Create a new Cmd object
        cmd = Cmd()
        
        # Set up the basic structure
        cmd.header = Cmd.Header()
        cmd.resources = Cmd.Resources()
        cmd.components = Cmd.Components()
        
        # Create the BLAM bundle repository component
        repo = Cmd.Components.BlamBundleRepositoryV10()
        cmd.components.blam_bundle_repository_v10 = repo
        
        # Set up the main sections
        repo.bundle_general_info = cls._export_general_info(bundle)
        repo.bundle_publication_info = cls._export_publication_info(bundle)
        repo.bundle_administrative_info = cls._export_administrative_info(bundle)
        repo.bundle_structural_info = cls._export_structural_info(bundle)
        repo.project_info = cls._export_project_info(bundle)
        repo.bundle_data_info = cls._export_data_info(bundle)
        
        # Set metadata license
        repo.md_license = bundle.md_license
        repo.md_license.uri = bundle.md_license_uri
        
        return cmd
    
    @classmethod
    def _export_general_info(cls, bundle: BLAMBundle) -> Any:
        """Export general info section"""
        # Implementation would go here
        pass
    
    @classmethod
    def _export_publication_info(cls, bundle: BLAMBundle) -> Any:
        """Export publication info section"""
        # Implementation would go here
        pass
    
    @classmethod
    def _export_administrative_info(cls, bundle: BLAMBundle) -> Any:
        """Export administrative info section"""
        # Implementation would go here
        pass
    
    @classmethod
    def _export_structural_info(cls, bundle: BLAMBundle) -> Any:
        """Export structural info section"""
        # Implementation would go here
        pass
    
    @classmethod
    def _export_project_info(cls, bundle: BLAMBundle) -> Any:
        """Export project info section"""
        # Implementation would go here
        pass
    
    @classmethod
    def _export_data_info(cls, bundle: BLAMBundle) -> Any:
        """Export data info section"""
        # Implementation would go here
        pass


# Simplified interface functions
def import_bundle_from_xml(xml_content: str) -> BLAMBundle:
    """Import a bundle from XML content"""
    return BundleImporter.import_from_xml(xml_content)

def export_bundle_to_xml(bundle: BLAMBundle) -> str:
    """Export a bundle to XML content"""
    return BundleExporter.export_to_xml(bundle)