import logging
import traceback
from django.db import transaction
from django.db.models import Count, Q

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleStructuralInfo, BundleResources, MediaResource, WrittenResource, OtherResource
)

logger = logging.getLogger(__name__)

class CleanupService:
    """
    Service for cleaning up the BLAM database models.
    Provides methods to fix data integrity issues and cleanup orphaned records.
    """
    
    @staticmethod
    def cleanup_bundle_resources():
        """
        Fix bundle resources that are not properly linked to their structural info.
        
        Returns:
            dict: Statistics about the cleanup operations performed
        """
        stats = {
            'fixed_resources': 0,
            'orphaned_resources_removed': 0,
            'empty_resource_containers_removed': 0,
            'bundles_without_resources': 0,
            'errors': []
        }
        
        logger.info("Starting bundle resources cleanup...")
        
        try:
            with transaction.atomic():
                # 1. Find bundles with structural_info but no resources
                bundles_missing_resources = Bundle.objects.filter(
                    structural_info__isnull=False, 
                    structural_info__resources__isnull=True
                )
                stats['bundles_without_resources'] = bundles_missing_resources.count()
                logger.info(f"Found {stats['bundles_without_resources']} bundles without resources")
                
                # Create resource containers for bundles that don't have them
                for bundle in bundles_missing_resources:
                    try:
                        # Create a new resources container
                        resources = BundleResources.objects.create()
                        # Link it to the bundle's structural info
                        bundle.structural_info.resources = resources
                        bundle.structural_info.save()
                        stats['fixed_resources'] += 1
                        logger.debug(f"Created resources container for bundle {bundle.id}")
                    except Exception as e:
                        error_msg = f"Error fixing resources for bundle {bundle.id}: {e}"
                        logger.error(error_msg)
                        logger.debug(traceback.format_exc())
                        stats['errors'].append(f"Bundle {bundle.id}: {str(e)}")
                
                # 2. Find orphaned resource containers (not linked to any structural info)
                orphaned_resources = BundleResources.objects.filter(
                    structural_info__isnull=True
                )
                stats['orphaned_resources_removed'] = orphaned_resources.count()
                logger.info(f"Found {stats['orphaned_resources_removed']} orphaned resource containers")
                
                if stats['orphaned_resources_removed'] > 0:
                    logger.warning(f"Deleting {stats['orphaned_resources_removed']} orphaned resource containers")
                    orphaned_resources.delete()
                
                # 3. Find empty resource containers and populate stats
                empty_resources = BundleResources.objects.annotate(
                    media_count=Count('bundle_media_resources'),
                    written_count=Count('bundle_written_resources'),
                    other_count=Count('bundle_other_resources')
                ).filter(
                    media_count=0,
                    written_count=0,
                    other_count=0
                )
                stats['empty_resource_containers'] = empty_resources.count()
                logger.info(f"Found {stats['empty_resource_containers']} empty resource containers")
                
                # 4. Find orphaned resources (not linked to any BundleResources)
                orphaned_media = MediaResource.objects.filter(
                    bundleresources__isnull=True
                )
                orphaned_written = WrittenResource.objects.filter(
                    bundleresources__isnull=True
                )
                orphaned_other = OtherResource.objects.filter(
                    bundleresources__isnull=True
                )
                
                stats['orphaned_media_removed'] = orphaned_media.count()
                stats['orphaned_written_removed'] = orphaned_written.count()
                stats['orphaned_other_removed'] = orphaned_other.count()
                
                logger.info(f"Found {stats['orphaned_media_removed']} orphaned media resources")
                logger.info(f"Found {stats['orphaned_written_removed']} orphaned written resources")
                logger.info(f"Found {stats['orphaned_other_removed']} orphaned other resources")
                
                # Delete orphaned resources
                if stats['orphaned_media_removed'] > 0:
                    logger.warning(f"Deleting {stats['orphaned_media_removed']} orphaned media resources")
                    orphaned_media.delete()
                
                if stats['orphaned_written_removed'] > 0:
                    logger.warning(f"Deleting {stats['orphaned_written_removed']} orphaned written resources")
                    orphaned_written.delete()
                
                if stats['orphaned_other_removed'] > 0:
                    logger.warning(f"Deleting {stats['orphaned_other_removed']} orphaned other resources")
                    orphaned_other.delete()
                
                # Log summary
                logger.info(f"Bundle resources cleanup completed: {stats}")
                
        except Exception as e:
            error_msg = f"Error during bundle resources cleanup: {e}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            stats['errors'].append(f"Global error: {str(e)}")
        
        return stats
    
    @staticmethod
    def fix_collection_bundle_links():
        """
        Fix collection-bundle links that may be broken or inconsistent.
        
        Returns:
            dict: Statistics about the cleanup operations performed
        """
        stats = {
            'fixed_links': 0,
            'errors': []
        }
        
        logger.info("Starting collection-bundle links cleanup...")
        
        try:
            with transaction.atomic():
                # Find collections with bundles that don't properly reference back to the collection
                collections = Collection.objects.all()
                logger.info(f"Checking {collections.count()} collections for broken bundle links")
                
                for collection in collections:
                    # Get bundles linked via bundle_collection reverse relationship
                    linked_bundles = collection.bundle_collection.all()
                    logger.debug(f"Collection {collection.id} has {linked_bundles.count()} linked bundles")
                    
                    for structural_info in linked_bundles:
                        try:
                            # Ensure each BundleStructuralInfo correctly points to this collection
                            if structural_info.is_member_of_collection_id != collection.id:
                                logger.warning(f"Found mismatched collection link in BundleStructuralInfo {structural_info.id}. " 
                                              f"Expected {collection.id}, found {structural_info.is_member_of_collection_id}")
                                structural_info.is_member_of_collection = collection
                                structural_info.save()
                                stats['fixed_links'] += 1
                        except Exception as e:
                            error_msg = f"Error fixing link for collection {collection.id}, bundle structural info {structural_info.id}: {e}"
                            logger.error(error_msg)
                            logger.debug(traceback.format_exc())
                            stats['errors'].append(f"Collection {collection.id}, BundleStructuralInfo {structural_info.id}: {str(e)}")
                
                # Log summary
                logger.info(f"Collection-bundle link cleanup completed: Fixed {stats['fixed_links']} links")
                
        except Exception as e:
            error_msg = f"Error during collection-bundle link cleanup: {e}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            stats['errors'].append(f"Global error: {str(e)}")
        
        return stats
    
    @staticmethod
    def run_full_cleanup():
        """
        Run all cleanup operations in sequence.
        
        Returns:
            dict: Combined statistics from all cleanup operations
        """
        logger.info("Starting full cleanup process...")
        
        results = {
            'bundle_resources': CleanupService.cleanup_bundle_resources(),
            'collection_bundle_links': CleanupService.fix_collection_bundle_links()
        }
        
        logger.info("Full cleanup process completed")
        return results
    
    @staticmethod
    def get_database_statistics():
        """
        Get statistics about the BLAM database models.
        
        Returns:
            dict: Statistics about collections, bundles, and resources
        """
        from django.db.models import Count
        
        logger.info("Gathering database statistics...")
        
        stats = {
            'collections': {
                'total': Collection.objects.count(),
                'with_bundles': Collection.objects.filter(bundle_collection__isnull=False).distinct().count()
            },
            'bundles': {
                'total': Bundle.objects.count(),
                'with_collections': Bundle.objects.filter(structural_info__is_member_of_collection__isnull=False).count(),
                'without_collections': Bundle.objects.filter(structural_info__is_member_of_collection__isnull=True).count(),
                'with_resources': Bundle.objects.filter(structural_info__resources__isnull=False).count(),
                'without_resources': Bundle.objects.filter(structural_info__isnull=False, structural_info__resources__isnull=True).count()
            },
            'resources': {
                'total_containers': BundleResources.objects.count(),
                'media_resources': MediaResource.objects.count(),
                'written_resources': WrittenResource.objects.count(),
                'other_resources': OtherResource.objects.count(),
                'total_resources': MediaResource.objects.count() + WrittenResource.objects.count() + OtherResource.objects.count()
            }
        }
        
        # Get bundles with structural info
        stats['bundles']['with_structural_info'] = Bundle.objects.filter(structural_info__isnull=False).count()
        
        # Get empty resource containers
        empty_resources = BundleResources.objects.annotate(
            media_count=Count('bundle_media_resources'),
            written_count=Count('bundle_written_resources'),
            other_count=Count('bundle_other_resources')
        ).filter(
            media_count=0,
            written_count=0,
            other_count=0
        ).count()
        
        stats['resources']['empty_containers'] = empty_resources
        
        logger.debug(f"Database statistics: {stats}")
        return stats
    
    @staticmethod
    def delete_all_data():
        """
        Delete all collections, bundles, and related data.
        CAUTION: This is a destructive operation and should be used with care.
        
        Returns:
            dict: Statistics about what was deleted
        """
        stats = {
            'deleted': {
                'collections': 0,
                'bundles': 0,
                'structural_infos': 0,
                'resource_containers': 0,
                'media_resources': 0,
                'written_resources': 0,
                'other_resources': 0
            },
            'errors': []
        }
        
        logger.warning("Starting deletion of ALL data from BLAM database")
        
        try:
            with transaction.atomic():
                # Count items before deletion
                stats['deleted']['collections'] = Collection.objects.count()
                stats['deleted']['bundles'] = Bundle.objects.count()
                stats['deleted']['structural_infos'] = BundleStructuralInfo.objects.count()
                stats['deleted']['resource_containers'] = BundleResources.objects.count()
                stats['deleted']['media_resources'] = MediaResource.objects.count()
                stats['deleted']['written_resources'] = WrittenResource.objects.count()
                stats['deleted']['other_resources'] = OtherResource.objects.count()
                
                logger.warning(f"About to delete {stats['deleted']['collections']} collections, "
                              f"{stats['deleted']['bundles']} bundles, and "
                              f"{stats['deleted']['media_resources'] + stats['deleted']['written_resources'] + stats['deleted']['other_resources']} resources")
                
                # Delete everything - cascade will handle related objects
                Collection.objects.all().delete()
                Bundle.objects.all().delete()
                BundleStructuralInfo.objects.all().delete()
                BundleResources.objects.all().delete()
                MediaResource.objects.all().delete()
                WrittenResource.objects.all().delete()
                OtherResource.objects.all().delete()
                
                logger.warning(f"Successfully deleted all BLAM data: {stats}")
        except Exception as e:
            error_msg = f"Error during data deletion: {e}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            stats['errors'].append(f"Global error: {str(e)}")
        
        return stats

    @staticmethod
    def delete_collections_only():
        """
        Delete only collections but keep bundles and resources intact.
        This will orphan any bundles that were part of the deleted collections.
        
        Returns:
            dict: Statistics about what was deleted
        """
        stats = {
            'deleted': {
                'collections': 0,
                'collection_headers': 0,
                'collection_general_infos': 0,
                'collection_publication_infos': 0,
                'collection_administrative_infos': 0,
                'collection_structural_infos': 0
            },
            'orphaned': {
                'bundles': 0
            },
            'errors': []
        }
        
        logger.warning("Starting deletion of collections only")
        
        try:
            with transaction.atomic():
                # Count bundles that will become orphaned
                stats['orphaned']['bundles'] = Bundle.objects.filter(
                    structural_info__is_member_of_collection__isnull=False
                ).count()
                
                # Count collections before deletion
                stats['deleted']['collections'] = Collection.objects.count()
                
                logger.warning(f"About to delete {stats['deleted']['collections']} collections and orphan {stats['orphaned']['bundles']} bundles")
                
                # Delete all collections - cascade will handle related collection-specific objects
                Collection.objects.all().delete()
                
                logger.warning(f"Successfully deleted all collections: {stats}")
        except Exception as e:
            error_msg = f"Error during collections deletion: {e}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            stats['errors'].append(f"Global error: {str(e)}")
        
        return stats

    @staticmethod
    def delete_bundles_only():
        """
        Delete only bundles and their resources but keep collections intact.
        
        Returns:
            dict: Statistics about what was deleted
        """
        stats = {
            'deleted': {
                'bundles': 0,
                'bundle_headers': 0,
                'bundle_general_infos': 0,
                'bundle_publication_infos': 0,
                'bundle_administrative_infos': 0,
                'bundle_structural_infos': 0,
                'resource_containers': 0,
                'media_resources': 0,
                'written_resources': 0,
                'other_resources': 0
            },
            'affected': {
                'collections': 0
            },
            'errors': []
        }
        
        logger.warning("Starting deletion of bundles only")
        
        try:
            with transaction.atomic():
                # Count affected collections
                stats['affected']['collections'] = Collection.objects.filter(
                    bundle_collection__isnull=False
                ).distinct().count()
                
                # Count items before deletion
                stats['deleted']['bundles'] = Bundle.objects.count()
                stats['deleted']['resource_containers'] = BundleResources.objects.count()
                stats['deleted']['media_resources'] = MediaResource.objects.count()
                stats['deleted']['written_resources'] = WrittenResource.objects.count()
                stats['deleted']['other_resources'] = OtherResource.objects.count()
                
                logger.warning(f"About to delete {stats['deleted']['bundles']} bundles and their resources, "
                              f"affecting {stats['affected']['collections']} collections")
                
                # Delete all bundles and resources - cascade will handle related objects
                Bundle.objects.all().delete()
                BundleStructuralInfo.objects.all().delete()
                BundleResources.objects.all().delete()
                MediaResource.objects.all().delete()
                WrittenResource.objects.all().delete()
                OtherResource.objects.all().delete()
                
                logger.warning(f"Successfully deleted all bundles and resources: {stats}")
        except Exception as e:
            error_msg = f"Error during bundles deletion: {e}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            stats['errors'].append(f"Global error: {str(e)}")
        
        return stats 