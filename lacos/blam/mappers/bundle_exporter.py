from typing import Any, List, Optional
from django.contrib.gis.geos import Point

from lacos.blam.models.bundle import (
    BLAMBundle, BundleIdentifier, ObjectLanguage, 
    ObjectLanguageAlternativeName, BundleLocation,
    Creator, Contributor, License, RightsHolder,
    MediaResource, WrittenResource, OtherResource,
    BundleKeyword, Project, Funder, SegmentationUnit,
    TranscriptionType, TranslationLanguage
)
from lacos.blam.blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd, BundleIdIdentifierType, BundleIsMemberOfCollectionIdentifierType,
    CreatorNameIdentifierIdentifierType, ContributorNameIdentifierIdentifierType,
    FunderIdentifierIdentifierType, RightsHolderIdentifierIdentifierType,
    SimpletypeAccess51, ComplextypeAccess51
)
from xsdata.models.datatype import XmlDate
from lacos.blam.mappers.bundle_importer import BundleImporter

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
    def _export_general_info(cls, bundle: BLAMBundle) -> Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo:
        """Export general info section"""
        general_info = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo()
        
        # Set basic fields
        general_info.bundle_version = bundle.bundle_version
        general_info.bundle_display_title = bundle.bundle_display_title
        general_info.bundle_description = bundle.bundle_description
        general_info.bundle_recording_date = bundle.bundle_recording_date
        
        # Export bundle IDs
        for bundle_id in bundle.bundle_ids.all():
            id_obj = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleId()
            id_obj.value = bundle_id.value
            if bundle_id.identifier_type:
                id_obj.identifier_type = BundleIdIdentifierType(bundle_id.identifier_type)
            general_info.bundle_id.append(id_obj)
        
        # Export keywords
        if bundle.keywords.exists():
            keywords = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleKeywords()
            for keyword in bundle.keywords.all():
                keywords.bundle_keyword.append(keyword.keyword)
            general_info.bundle_keywords = keywords
        
        # Export object languages
        languages = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages()
        for lang in bundle.languages.all():
            obj_lang = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages.BundleObjectLanguage()
            obj_lang.object_language_display_name = lang.display_name
            obj_lang.object_language_name = lang.name
            obj_lang.object_language_iso639_3_code = lang.iso_639_3_code
            obj_lang.object_language_glottolog_code = lang.glottolog_code
            
            # Set language taxonomy
            taxonomy = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages.BundleObjectLanguage.ObjectLanguageTaxonomy()
            taxonomy.object_language_language_family.append(lang.language_family)
            obj_lang.object_language_taxonomy = taxonomy
            
            # Add alternative names if any
            if lang.alternative_names.exists():
                alt_names = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages.BundleObjectLanguage.ObjectLanguageAlternativeNames()
                for alt_name in lang.alternative_names.all():
                    alt_names.object_language_alternative_name.append(alt_name.name)
                obj_lang.object_language_alternative_names = alt_names
            
            languages.bundle_object_language.append(obj_lang)
        
        general_info.bundle_object_languages = languages
        
        # Export location if exists
        if hasattr(bundle, 'location') and bundle.location:
            location = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleLocation()
            loc = bundle.location
            
            if loc.geo_location:
                # Convert Point object to string format "lat lon"
                location.bundle_geo_location = f"{loc.geo_location.y} {loc.geo_location.x}"
            
            location.bundle_location_name = loc.location_name or ""
            location.bundle_location_facet = loc.location_facet or ""
            location.bundle_region_name = loc.region_name
            location.bundle_region_facet = loc.region_facet
            location.bundle_country_name = loc.country_name
            location.bundle_country_facet = loc.country_facet
            location.bundle_country_code = loc.country_code
            
            general_info.bundle_location = location
        
        return general_info
    
    @classmethod
    def _export_publication_info(cls, bundle: BLAMBundle) -> Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo:
        """Export publication info section"""
        pub_info = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo()
        
        # Set basic fields
        pub_info.bundle_publication_year = XmlDate(year=bundle.bundle_publication_year)
        pub_info.bundle_data_provider = bundle.bundle_data_provider
        
        # Export creators
        creators = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators()
        for creator in bundle.creators.all().order_by('order'):
            creator_obj = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators.BundleCreator()
            
            # Set creator name
            creator_name = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators.BundleCreator.CreatorName()
            creator_name.creator_family_name = creator.family_name
            creator_name.creator_given_name = creator.given_name or ""
            creator_obj.creator_name = creator_name
            
            # Set order if available
            if creator.order is not None:
                creator_obj.order = creator.order
            
            # Set name identifier if available
            if creator.name_identifier:
                id_obj = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators.BundleCreator.CreatorNameIdentifier()
                id_obj.value = creator.name_identifier
                if creator.name_identifier_type:
                    id_obj.identifier_type = CreatorNameIdentifierIdentifierType(creator.name_identifier_type)
                creator_obj.creator_name_identifier.append(id_obj)
            
            # Set affiliation if available
            if creator.affiliation:
                creator_obj.creator_affiliation.append(creator.affiliation)
            
            creators.bundle_creator.append(creator_obj)
        
        pub_info.bundle_creators = creators
        
        # Export contributors if any
        if bundle.contributors.exists():
            contributors = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors()
            for contributor in bundle.contributors.all():
                contributor_obj = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors.BundleContributor()
                
                # Set contributor name
                contributor_name = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors.BundleContributor.ContributorName()
                contributor_name.contributor_family_name = contributor.family_name
                contributor_name.contributor_given_name = contributor.given_name or ""
                contributor_obj.contributor_name = contributor_name
                
                # Set role
                contributor_obj.contributor_role.append(contributor.role)
                
                # Set name identifier if available
                if contributor.name_identifier:
                    id_obj = Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors.BundleContributor.ContributorNameIdentifier()
                    id_obj.value = contributor.name_identifier
                    if contributor.name_identifier_type:
                        id_obj.identifier_type = ContributorNameIdentifierIdentifierType(contributor.name_identifier_type)
                    contributor_obj.contributor_name_identifier.append(id_obj)
                
                # Set affiliation if available
                if contributor.affiliation:
                    contributor_obj.contributor_affiliation.append(contributor.affiliation)
                
                contributors.bundle_contributor.append(contributor_obj)
            
            pub_info.bundle_contributors = contributors
        
        return pub_info
    
    @classmethod
    def _export_administrative_info(cls, bundle: BLAMBundle) -> Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo:
        """Export administrative info section"""
        admin_info = Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo()
        
        # Set access
        access = ComplextypeAccess51()
        access.value = SimpletypeAccess51(bundle.access)
        admin_info.access = access
        
        # Set availability date
        admin_info.availability_date = XmlDate(
            year=bundle.availability_date.year,
            month=bundle.availability_date.month,
            day=bundle.availability_date.day
        )
        
        # Export licenses
        for license in bundle.licenses.all():
            license_obj = Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo.License()
            license_obj.license_name = license.name
            license_obj.license_identifier = license.identifier
            admin_info.license.append(license_obj)
        
        # Export rights holders
        for holder in bundle.rights_holders.all():
            holder_obj = Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo.RightsHolder()
            holder_obj.rights_holder_name = holder.name
            
            if holder.identifier:
                id_obj = Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo.RightsHolder.RightsHolderIdentifier()
                id_obj.value = holder.identifier
                if holder.identifier_type:
                    id_obj.identifier_type = RightsHolderIdentifierIdentifierType(holder.identifier_type)
                holder_obj.rights_holder_identifier.append(id_obj)
            
            admin_info.rights_holder.append(holder_obj)
        
        return admin_info
    
    @classmethod
    def _export_structural_info(cls, bundle: BLAMBundle) -> Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo:
        """Export structural info section"""
        structural_info = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo()
        
        # Set collection membership
        collection = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleIsMemberOfCollection()
        collection.value = bundle.bundle_is_member_of_collection
        collection.identifier_type = BundleIsMemberOfCollectionIdentifierType(bundle.bundle_is_member_of_collection_type)
        structural_info.bundle_is_member_of_collection = collection
        
        # Export resources
        resources = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources()
        
        # Export media resources
        for media in bundle.mediaresources.all():
            media_obj = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources.MediaResource()
            media_obj.file_name = media.file_name
            media_obj.file_pid = media.file_pid
            media_obj.mime_type = media.mime_type
            media_obj.file_length = media.file_length
            if media.file_description:
                media_obj.file_description = media.file_description
            if media.ref:
                media_obj.ref.append(media.ref)
            resources.media_resource.append(media_obj)
        
        # Export written resources
        for written in bundle.writtenresources.all():
            written_obj = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources.WrittenResource()
            written_obj.file_name = written.file_name
            written_obj.file_pid = written.file_pid
            written_obj.mime_type = written.mime_type
            if written.file_description:
                written_obj.file_description = written.file_description
            if written.ref:
                written_obj.ref.append(written.ref)
            
            # Add annotations if any
            for annotation_of in written.is_annotation_of.all():
                written_obj.is_annotation_of.append(annotation_of.ref)
            
            resources.written_resource.append(written_obj)
        
        # Export other resources
        for other in bundle.otherresources.all():
            other_obj = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources.OtherResource()
            other_obj.file_name = other.file_name
            other_obj.file_pid = other.file_pid
            other_obj.mime_type = other.mime_type
            if other.file_description:
                other_obj.file_description = other.file_description
            if other.ref:
                other_obj.ref.append(other.ref)
            resources.other_resource.append(other_obj)
        
        structural_info.bundle_resources = resources
        
        return structural_info
    
    @classmethod
    def _export_project_info(cls, bundle: BLAMBundle) -> Optional[Cmd.Components.BlamBundleRepositoryV10.ProjectInfo]:
        """Export project info section"""
        if not bundle.projects.exists():
            return None
        
        project_info = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo()
        
        for proj in bundle.projects.all():
            project_obj = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project()
            project_obj.project_display_name = proj.display_name
            project_obj.project_description = proj.description
            
            # Export funders if any
            if proj.funders.exists():
                funders = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project.FunderInfos()
                for funder in proj.funders.all():
                    funder_obj = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project.FunderInfos.FunderInfo()
                    funder_obj.funder_name = funder.name
                    
                    if funder.identifier:
                        id_obj = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project.FunderInfos.FunderInfo.FunderIdentifier()
                        id_obj.value = funder.identifier
                        if funder.identifier_type:
                            id_obj.identifier_type = FunderIdentifierIdentifierType(funder.identifier_type)
                        funder_obj.funder_identifier = id_obj
                    
                    if funder.grant_identifier:
                        funder_obj.grant_identifier = funder.grant_identifier
                    
                    if funder.grant_uri:
                        funder_obj.grant_uri = funder.grant_uri
                    
                    funders.funder_info.append(funder_obj)
                
                project_obj.funder_infos = funders
            
            project_info.project.append(project_obj)
        
        return project_info
    
    @classmethod
    def _export_data_info(cls, bundle: BLAMBundle) -> Optional[Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo]:
        """Export data info section"""
        # Check if any data info exists
        has_segmentation = SegmentationUnit.objects.filter(bundle=bundle).exists()
        has_transcription = TranscriptionType.objects.filter(bundle=bundle).exists()
        has_translation = TranslationLanguage.objects.filter(bundle=bundle).exists()
        
        if not (has_segmentation or has_transcription or has_translation):
            return None
        
        data_info = Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo()
        
        # Export segmentation units if any
        if has_segmentation:
            segmentation = Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo.SegmentationUnits()
            for unit in SegmentationUnit.objects.filter(bundle=bundle):
                segmentation.segmentation_unit.append(unit.unit)
            data_info.segmentation_units = segmentation
        
        # Export transcription types if any
        if has_transcription:
            transcription = Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo.TranscriptionTypes()
            for ttype in TranscriptionType.objects.filter(bundle=bundle):
                transcription.transcription_type.append(ttype.type)
            data_info.transcription_types = transcription
        
        # Export translation languages if any
        if has_translation:
            translation = Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo.TranslationLanguages()
            for tlang in TranslationLanguage.objects.filter(bundle=bundle):
                lang_obj = Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo.TranslationLanguages.TranslationLanguage()
                lang_obj.translation_language_name = tlang.name
                lang_obj.translation_language_code = tlang.code
                translation.translation_language.append(lang_obj)
            data_info.translation_languages = translation
        
        return data_info


# Simplified interface function
def export_bundle_to_xml(bundle: BLAMBundle) -> str:
    """Export a bundle to XML content"""
    return BundleExporter.export_to_xml(bundle)

def import_bundle_from_xml(xml_content: str) -> BLAMBundle:
    """Import a bundle from XML content"""
    return BundleImporter.import_from_xml(xml_content)