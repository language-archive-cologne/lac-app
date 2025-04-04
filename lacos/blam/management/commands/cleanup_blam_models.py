import logging
from django.core.management.base import BaseCommand

from lacos.blam.services.cleanup_service import CleanupService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Cleans up the database by fixing bundle resources, collection-bundle links, and orphaned metadata'

    def add_arguments(self, parser):
        parser.add_argument(
            '--resources-only',
            action='store_true',
            help='Only fix bundle resources',
        )
        parser.add_argument(
            '--links-only',
            action='store_true',
            help='Only fix collection-bundle links',
        )
        parser.add_argument(
            '--metadata-only',
            action='store_true',
            help='Only clean up orphaned metadata records',
        )
        parser.add_argument(
            '--headers-only',
            action='store_true',
            help='Only clean up orphaned collection headers',
        )
        parser.add_argument(
            '--publication-info-only',
            action='store_true',
            help='Only clean up orphaned publication info records',
        )
        parser.add_argument(
            '--general-info-only',
            action='store_true',
            help='Only clean up orphaned general info records',
        )
        parser.add_argument(
            '--admin-info-only',
            action='store_true',
            help='Only clean up orphaned administrative info records',
        )
        parser.add_argument(
            '--structural-info-only',
            action='store_true',
            help='Only clean up orphaned structural info records',
        )
        parser.add_argument(
            '--project-info-only',
            action='store_true',
            help='Only clean up orphaned project info records',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only report issues but do not fix them',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting database cleanup..."))
        
        # Determine which cleanup operations to run
        run_resources = not (options['links_only'] or options['metadata_only'] or 
                            options['headers_only'] or options['publication_info_only'] or
                            options['general_info_only'] or options['admin_info_only'] or
                            options['structural_info_only'] or options['project_info_only'])
        
        run_links = not (options['resources_only'] or options['metadata_only'] or 
                        options['headers_only'] or options['publication_info_only'] or
                        options['general_info_only'] or options['admin_info_only'] or
                        options['structural_info_only'] or options['project_info_only'])
        
        run_metadata = options['metadata_only'] or not (options['resources_only'] or options['links_only'] or
                                                      options['headers_only'] or options['publication_info_only'] or
                                                      options['general_info_only'] or options['admin_info_only'] or
                                                      options['structural_info_only'] or options['project_info_only'])
        
        run_headers = options['headers_only'] or (run_metadata and not (options['publication_info_only'] or 
                                                                     options['general_info_only'] or 
                                                                     options['admin_info_only'] or
                                                                     options['structural_info_only'] or
                                                                     options['project_info_only']))
        
        run_publication_info = options['publication_info_only'] or (run_metadata and not (options['headers_only'] or 
                                                                                       options['general_info_only'] or 
                                                                                       options['admin_info_only'] or
                                                                                       options['structural_info_only'] or
                                                                                       options['project_info_only']))
        
        run_general_info = options['general_info_only'] or (run_metadata and not (options['headers_only'] or 
                                                                               options['publication_info_only'] or 
                                                                               options['admin_info_only'] or
                                                                               options['structural_info_only'] or
                                                                               options['project_info_only']))
        
        run_admin_info = options['admin_info_only'] or (run_metadata and not (options['headers_only'] or 
                                                                           options['publication_info_only'] or 
                                                                           options['general_info_only'] or
                                                                           options['structural_info_only'] or
                                                                           options['project_info_only']))
        
        run_structural_info = options['structural_info_only'] or (run_metadata and not (options['headers_only'] or 
                                                                                      options['publication_info_only'] or 
                                                                                      options['general_info_only'] or
                                                                                      options['admin_info_only'] or
                                                                                      options['project_info_only']))
        
        run_project_info = options['project_info_only'] or (run_metadata and not (options['headers_only'] or 
                                                                               options['publication_info_only'] or 
                                                                               options['general_info_only'] or
                                                                               options['admin_info_only'] or
                                                                               options['structural_info_only']))
        
        # Track overall statistics
        total_fixed = 0
        has_errors = False
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
        
        # Run bundle resources cleanup if requested
        if run_resources:
            self.stdout.write(self.style.NOTICE("Cleaning up bundle resources..."))
            if options['dry_run']:
                # For dry run, we need to inspect without modifying
                bundle_stats = self._dry_run_resources()
            else:
                bundle_stats = CleanupService.cleanup_bundle_resources()
                
            self._print_resource_stats(bundle_stats)
            total_fixed += bundle_stats.get('fixed_resources', 0)
            if bundle_stats.get('errors'):
                has_errors = True
        
        # Run collection-bundle links cleanup if requested
        if run_links:
            self.stdout.write(self.style.NOTICE("Cleaning up collection-bundle links..."))
            if options['dry_run']:
                # For dry run, we need to inspect without modifying
                link_stats = self._dry_run_links()
            else:
                link_stats = CleanupService.fix_collection_bundle_links()
                
            self._print_link_stats(link_stats)
            total_fixed += link_stats.get('fixed_links', 0)
            if link_stats.get('errors'):
                has_errors = True
        
        # Run collection headers cleanup if requested
        if run_headers:
            self.stdout.write(self.style.NOTICE("Cleaning up orphaned collection headers..."))
            if options['dry_run']:
                # For dry run, we need to inspect without modifying
                header_stats = self._dry_run_headers()
            else:
                header_stats = CleanupService.cleanup_orphaned_headers()
                
            self._print_header_stats(header_stats)
            total_fixed += header_stats.get('orphaned_headers_removed', 0) + header_stats.get('fixed_headers', 0)
            if header_stats.get('errors'):
                has_errors = True
        
        # Run publication info cleanup if requested
        if run_publication_info:
            self.stdout.write(self.style.NOTICE("Cleaning up orphaned publication info records..."))
            if options['dry_run']:
                # For dry run, we need to inspect without modifying
                pub_stats = self._dry_run_publication_info()
            else:
                pub_stats = CleanupService.cleanup_orphaned_publication_info()
                
            self._print_publication_stats(pub_stats)
            total_fixed += pub_stats.get('orphaned_publication_info_removed', 0) + pub_stats.get('fixed_publication_info', 0)
            if pub_stats.get('errors'):
                has_errors = True
        
        # Run general info cleanup if requested
        if run_general_info:
            self.stdout.write(self.style.NOTICE("Cleaning up orphaned general info records..."))
            if options['dry_run']:
                # For dry run, we need to inspect without modifying
                gen_stats = self._dry_run_general_info()
            else:
                gen_stats = CleanupService.cleanup_orphaned_general_info()
                
            self._print_general_info_stats(gen_stats)
            total_fixed += gen_stats.get('orphaned_general_info_removed', 0) + gen_stats.get('fixed_general_info', 0)
            if gen_stats.get('errors'):
                has_errors = True
        
        # Run administrative info cleanup if requested
        if run_admin_info:
            self.stdout.write(self.style.NOTICE("Cleaning up orphaned administrative info records..."))
            if options['dry_run']:
                # For dry run, we need to inspect without modifying
                admin_stats = self._dry_run_admin_info()
            else:
                admin_stats = CleanupService.cleanup_orphaned_admin_info()
                
            self._print_admin_info_stats(admin_stats)
            total_fixed += admin_stats.get('orphaned_admin_info_removed', 0) + admin_stats.get('fixed_admin_info', 0)
            if admin_stats.get('errors'):
                has_errors = True
        
        # Run structural info cleanup if requested
        if run_structural_info:
            self.stdout.write(self.style.NOTICE("Cleaning up orphaned structural info records..."))
            if options['dry_run']:
                # For dry run, we need to inspect without modifying
                struct_stats = self._dry_run_structural_info()
            else:
                struct_stats = CleanupService.cleanup_orphaned_structural_info()
                
            self._print_structural_info_stats(struct_stats)
            total_fixed += struct_stats.get('orphaned_structural_info_removed', 0) + struct_stats.get('fixed_structural_info', 0)
            if struct_stats.get('errors'):
                has_errors = True
        
        # Run project info cleanup if requested
        if run_project_info:
            self.stdout.write(self.style.NOTICE("Cleaning up orphaned project info records..."))
            if options['dry_run']:
                # For dry run, we need to inspect without modifying
                proj_stats = self._dry_run_project_info()
            else:
                proj_stats = CleanupService.cleanup_orphaned_project_info()
                
            self._print_project_info_stats(proj_stats)
            total_fixed += proj_stats.get('orphaned_project_info_removed', 0) + proj_stats.get('fixed_project_info', 0)
            if proj_stats.get('errors'):
                has_errors = True
        
        # Print summary
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f"Dry run completed. {total_fixed} issues found that would be fixed."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Database cleanup completed. {total_fixed} issues fixed."))
        
        if has_errors:
            self.stdout.write(self.style.WARNING("Errors were encountered during cleanup. Check the logs for details."))
            return 1
        return 0
    
    def _print_resource_stats(self, stats):
        """Format and print the bundle resources cleanup statistics."""
        self.stdout.write(f"  Bundles without resources: {stats.get('bundles_without_resources', 0)}")
        self.stdout.write(f"  Fixed resources: {stats.get('fixed_resources', 0)}")
        self.stdout.write(f"  Orphaned resources removed: {stats.get('orphaned_resources_removed', 0)}")
        self.stdout.write(f"  Empty resource containers: {stats.get('empty_resource_containers', 0)}")
        self.stdout.write(f"  Orphaned media resources removed: {stats.get('orphaned_media_removed', 0)}")
        self.stdout.write(f"  Orphaned written resources removed: {stats.get('orphaned_written_removed', 0)}")
        self.stdout.write(f"  Orphaned other resources removed: {stats.get('orphaned_other_removed', 0)}")
        
        if stats.get('errors'):
            self.stdout.write(self.style.ERROR(f"  Errors: {len(stats['errors'])}"))
            for error in stats['errors'][:5]:  # Show only first 5 errors to avoid flooding
                self.stdout.write(self.style.ERROR(f"    - {error}"))
            if len(stats['errors']) > 5:
                self.stdout.write(self.style.ERROR(f"    ... {len(stats['errors']) - 5} more errors (see logs)"))
    
    def _print_link_stats(self, stats):
        """Format and print the collection-bundle links cleanup statistics."""
        self.stdout.write(f"  Fixed links: {stats.get('fixed_links', 0)}")
        
        if stats.get('errors'):
            self.stdout.write(self.style.ERROR(f"  Errors: {len(stats['errors'])}"))
            for error in stats['errors'][:5]:  # Show only first 5 errors to avoid flooding
                self.stdout.write(self.style.ERROR(f"    - {error}"))
            if len(stats['errors']) > 5:
                self.stdout.write(self.style.ERROR(f"    ... {len(stats['errors']) - 5} more errors (see logs)"))
    
    def _print_header_stats(self, stats):
        """Format and print the collection headers cleanup statistics."""
        self.stdout.write(f"  Orphaned headers removed: {stats.get('orphaned_headers_removed', 0)}")
        self.stdout.write(f"  Fixed headers: {stats.get('fixed_headers', 0)}")
        
        if stats.get('errors'):
            self.stdout.write(self.style.ERROR(f"  Errors: {len(stats['errors'])}"))
            for error in stats['errors'][:5]:
                self.stdout.write(self.style.ERROR(f"    - {error}"))
            if len(stats['errors']) > 5:
                self.stdout.write(self.style.ERROR(f"    ... {len(stats['errors']) - 5} more errors (see logs)"))
    
    def _print_publication_stats(self, stats):
        """Format and print the publication info cleanup statistics."""
        self.stdout.write(f"  Orphaned publication info records removed: {stats.get('orphaned_publication_info_removed', 0)}")
        self.stdout.write(f"  Fixed publication info records: {stats.get('fixed_publication_info', 0)}")
        
        if stats.get('errors'):
            self.stdout.write(self.style.ERROR(f"  Errors: {len(stats['errors'])}"))
            for error in stats['errors'][:5]:
                self.stdout.write(self.style.ERROR(f"    - {error}"))
            if len(stats['errors']) > 5:
                self.stdout.write(self.style.ERROR(f"    ... {len(stats['errors']) - 5} more errors (see logs)"))
    
    def _print_general_info_stats(self, stats):
        """Format and print the general info cleanup statistics."""
        self.stdout.write(f"  Orphaned general info records removed: {stats.get('orphaned_general_info_removed', 0)}")
        self.stdout.write(f"  Fixed general info records: {stats.get('fixed_general_info', 0)}")
        
        if stats.get('errors'):
            self.stdout.write(self.style.ERROR(f"  Errors: {len(stats['errors'])}"))
            for error in stats['errors'][:5]:
                self.stdout.write(self.style.ERROR(f"    - {error}"))
            if len(stats['errors']) > 5:
                self.stdout.write(self.style.ERROR(f"    ... {len(stats['errors']) - 5} more errors (see logs)"))
    
    def _print_admin_info_stats(self, stats):
        """Format and print the administrative info cleanup statistics."""
        self.stdout.write(f"  Orphaned administrative info records removed: {stats.get('orphaned_admin_info_removed', 0)}")
        self.stdout.write(f"  Fixed administrative info records: {stats.get('fixed_admin_info', 0)}")
        
        if stats.get('errors'):
            self.stdout.write(self.style.ERROR(f"  Errors: {len(stats['errors'])}"))
            for error in stats['errors'][:5]:
                self.stdout.write(self.style.ERROR(f"    - {error}"))
            if len(stats['errors']) > 5:
                self.stdout.write(self.style.ERROR(f"    ... {len(stats['errors']) - 5} more errors (see logs)"))
    
    def _print_structural_info_stats(self, stats):
        """Format and print the structural info cleanup statistics."""
        self.stdout.write(f"  Orphaned structural info records removed: {stats.get('orphaned_structural_info_removed', 0)}")
        self.stdout.write(f"  Fixed structural info records: {stats.get('fixed_structural_info', 0)}")
        
        if stats.get('errors'):
            self.stdout.write(self.style.ERROR(f"  Errors: {len(stats['errors'])}"))
            for error in stats['errors'][:5]:
                self.stdout.write(self.style.ERROR(f"    - {error}"))
            if len(stats['errors']) > 5:
                self.stdout.write(self.style.ERROR(f"    ... {len(stats['errors']) - 5} more errors (see logs)"))
    
    def _print_project_info_stats(self, stats):
        """Format and print the project info cleanup statistics."""
        self.stdout.write(f"  Orphaned project info records removed: {stats.get('orphaned_project_info_removed', 0)}")
        self.stdout.write(f"  Fixed project info records: {stats.get('fixed_project_info', 0)}")
        
        if stats.get('errors'):
            self.stdout.write(self.style.ERROR(f"  Errors: {len(stats['errors'])}"))
            for error in stats['errors'][:5]:
                self.stdout.write(self.style.ERROR(f"    - {error}"))
            if len(stats['errors']) > 5:
                self.stdout.write(self.style.ERROR(f"    ... {len(stats['errors']) - 5} more errors (see logs)"))
    
    def _dry_run_resources(self):
        """Non-destructive inspection of bundle resources issues."""
        from django.db.models import Count
        from lacos.blam.models.bundle.bundle_repository import Bundle
        from lacos.blam.models.bundle.bundle_structural_info import BundleResources, MediaResource, WrittenResource, OtherResource
        
        stats = {
            'bundles_without_resources': 0,
            'orphaned_resources_removed': 0,
            'empty_resource_containers': 0,
            'orphaned_media_removed': 0,
            'orphaned_written_removed': 0,
            'orphaned_other_removed': 0,
            'fixed_resources': 0,
            'errors': []
        }
        
        # Count bundles with structural_info but no resources
        bundles_missing_resources = Bundle.objects.filter(
            structural_info__isnull=False, 
            structural_info__resources__isnull=True
        )
        stats['bundles_without_resources'] = bundles_missing_resources.count()
        stats['fixed_resources'] = stats['bundles_without_resources']  # In a real run, we'd fix these
        
        # Count orphaned resource containers (not linked to any structural info)
        orphaned_resources = BundleResources.objects.filter(
            structural_info__isnull=True
        )
        stats['orphaned_resources_removed'] = orphaned_resources.count()
        
        # Count empty resource containers
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
        
        # Count orphaned resources (not linked to any BundleResources)
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
        
        return stats
    
    def _dry_run_links(self):
        """Non-destructive inspection of collection-bundle link issues."""
        from lacos.blam.models.collection.collection_repository import Collection
        
        stats = {
            'fixed_links': 0,
            'errors': []
        }
        
        # Find collections with bundles that don't properly reference back
        collections = Collection.objects.all()
        incorrect_links = 0
        
        for collection in collections:
            # Get bundles linked via bundle_collection reverse relationship
            linked_bundles = collection.bundle_collection.all()
            
            for structural_info in linked_bundles:
                # Check if BundleStructuralInfo correctly points to this collection
                if structural_info.is_member_of_collection_id != collection.id:
                    incorrect_links += 1
        
        stats['fixed_links'] = incorrect_links  # In a real run, we'd fix these
        
        return stats
    
    def _dry_run_headers(self):
        """Non-destructive inspection of orphaned collection headers."""
        from lacos.blam.models.collection.collection_header import CollectionHeader
        from lacos.blam.models.collection.collection_repository import Collection
        
        stats = {
            'orphaned_headers_removed': 0,
            'fixed_headers': 0,
            'errors': []
        }
        
        # Find headers not linked to any collection
        orphaned_headers = CollectionHeader.objects.filter(
            collection_header_info__isnull=True
        )
        stats['orphaned_headers_removed'] = orphaned_headers.count()
        
        return stats
    
    def _dry_run_publication_info(self):
        """Non-destructive inspection of orphaned publication info records."""
        from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
        
        stats = {
            'orphaned_publication_info_removed': 0,
            'fixed_publication_info': 0,
            'errors': []
        }
        
        # Find publication info records not linked to any collection
        orphaned_pub_info = CollectionPublicationInfo.objects.filter(
            collection_publication_info__isnull=True
        )
        stats['orphaned_publication_info_removed'] = orphaned_pub_info.count()
        
        return stats
    
    def _dry_run_general_info(self):
        """Non-destructive inspection of orphaned general info records."""
        from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
        
        stats = {
            'orphaned_general_info_removed': 0,
            'fixed_general_info': 0,
            'errors': []
        }
        
        # Find general info records not linked to any collection
        orphaned_gen_info = CollectionGeneralInfo.objects.filter(
            collection_general_info__isnull=True
        )
        stats['orphaned_general_info_removed'] = orphaned_gen_info.count()
        
        return stats
    
    def _dry_run_admin_info(self):
        """Non-destructive inspection of orphaned administrative info records."""
        from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
        
        stats = {
            'orphaned_admin_info_removed': 0,
            'fixed_admin_info': 0,
            'errors': []
        }
        
        # Find administrative info records not linked to any collection
        orphaned_admin_info = CollectionAdministrativeInfo.objects.filter(
            collection_administrative_info__isnull=True
        )
        stats['orphaned_admin_info_removed'] = orphaned_admin_info.count()
        
        return stats
    
    def _dry_run_structural_info(self):
        """Non-destructive inspection of orphaned structural info records."""
        from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo
        
        stats = {
            'orphaned_structural_info_removed': 0,
            'fixed_structural_info': 0,
            'errors': []
        }
        
        # Find structural info records not linked to any collection
        orphaned_struct_info = CollectionStructuralInfo.objects.filter(
            collection_structural_info__isnull=True
        )
        stats['orphaned_structural_info_removed'] = orphaned_struct_info.count()
        
        return stats
    
    def _dry_run_project_info(self):
        """Non-destructive inspection of orphaned project info records."""
        from lacos.blam.models.base_project_info import ProjectInfo
        
        stats = {
            'orphaned_project_info_removed': 0,
            'fixed_project_info': 0,
            'errors': []
        }
        
        # Find project info records not linked to any collection
        orphaned_proj_info = ProjectInfo.objects.filter(
            collection_project_info__isnull=True
        )
        stats['orphaned_project_info_removed'] = orphaned_proj_info.count()
        
        return stats 