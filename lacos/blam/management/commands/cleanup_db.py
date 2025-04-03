import logging
from django.core.management.base import BaseCommand

from lacos.blam.services.cleanup_service import CleanupService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Cleans up the database by fixing bundle resources and collection-bundle links'

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
            '--dry-run',
            action='store_true',
            help='Only report issues but do not fix them',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting database cleanup..."))
        
        # Determine which cleanup operations to run
        run_resources = not options['links_only']
        run_links = not options['resources_only']
        
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