from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.generic import TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from django.template.loader import render_to_string
import logging

from lacos.blam.services.cleanup_service import CleanupService
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.common.mixins import HtmxTemplateHelperMixin
from lacos.storage.models import BackgroundTask

class DatabaseCleanupView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View to handle database cleanup operations.
    Only accessible to superusers.
    """
    
    def test_func(self):
        """Only allow superusers to access this view."""
        return self.request.user.is_superuser
    
    def post(self, request, *args, **kwargs):
        """
        Handle POST request to run database cleanup operations.
        Returns HTML response for HTMX with cleanup results.
        """
        # Run the cleanup operation
        results = CleanupService.run_full_cleanup()
        
        # Extract counts for a summary message
        bundle_results = results['bundle_resources']
        link_results = results['collection_bundle_links']
        
        fixed_resources = bundle_results.get('fixed_resources', 0)
        fixed_links = link_results.get('fixed_links', 0)
        
        # Prepare success message with summary counts
        message = f"Database cleanup completed. Fixed {fixed_resources} bundle resources and {fixed_links} collection-bundle links."
        
        # Check for errors
        errors = bundle_results.get('errors', []) + link_results.get('errors', [])
        if errors:
            message += f" Encountered {len(errors)} errors during cleanup."
        
        # Return HTML for results
        html = render_to_string('blam/dashboard/partials/cleanup_results.html', {
            'message': message,
            'bundle_results': bundle_results,
            'link_results': link_results,
            'errors': errors
        })
        
        return HttpResponse(html)


class DatabaseDeleteAllView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View to handle deleting all BLAM data.
    Only accessible to superusers.
    """
    
    def test_func(self):
        """Only allow superusers to access this view."""
        return self.request.user.is_superuser
    
    def post(self, request, *args, **kwargs):
        """
        Handle POST request to show confirmation before deleting all BLAM data.
        Returns HTML response for HTMX with confirmation dialog.
        """
        stats = CleanupService.get_database_statistics()
        
        # Return HTML for confirmation
        html = render_to_string('blam/dashboard/partials/confirm_delete_all.html', {
            'stats': stats,
            'action_url': reverse_lazy('database_delete_all_confirm')
        })
        
        return HttpResponse(html)


class DatabaseDeleteConfirmView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View to handle confirming deletion of all BLAM data.
    Only accessible to superusers.
    """
    
    def test_func(self):
        """Only allow superusers to access this view."""
        return self.request.user.is_superuser
    
    def post(self, request, *args, **kwargs):
        """
        Handle POST request to confirm and execute deletion of all BLAM data.
        Returns HTML response for HTMX with deletion results.
        """
        # Debug logging
        logger = logging.getLogger(__name__)
        logger.info(f"DatabaseDeleteConfirmView: Received POST request with data: {request.POST}")
        
        if 'confirm' not in request.POST or not request.POST.get('confirm'):
            logger.warning("DatabaseDeleteConfirmView: Confirmation checkbox not checked")
            message = "Deletion not confirmed. Please check the confirmation checkbox."
            html = render_to_string('blam/dashboard/partials/delete_results.html', {
                'message': message,
                'operation': 'all',
                'errors': ['Confirmation checkbox not checked']
            })
            return HttpResponse(html)
        
        logger.info("DatabaseDeleteConfirmView: Starting deletion of all data")
        
        # Run the deletion operation
        results = CleanupService.delete_all_data()
        logger.info(f"DatabaseDeleteConfirmView: Deletion completed with results: {results}")
        
        # Extract counts for a summary message
        deleted = results['deleted']
        
        # Prepare success message with summary counts
        message = f"Database reset completed. Deleted {deleted['collections']} collections, {deleted['bundles']} bundles, and {deleted['media_resources'] + deleted['written_resources'] + deleted['other_resources']} resources."
        
        # Check for errors
        errors = results.get('errors', [])
        if errors:
            message += f" Encountered {len(errors)} errors during deletion."
            logger.warning(f"DatabaseDeleteConfirmView: Encountered errors during deletion: {errors}")
        
        # Return HTML for results
        html = render_to_string('blam/dashboard/partials/delete_results.html', {
            'message': message,
            'deleted': deleted,
            'errors': errors,
            'operation': 'all',
            'debug': {
                'request_post': dict(request.POST),
                'results_summary': results,
                'csrf_token': request.META.get('CSRF_COOKIE', 'Not found')
            }
        })
        
        return HttpResponse(html)


class DatabaseDeleteCollectionsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View to handle deleting only collections while keeping bundles.
    Only accessible to superusers.
    """
    
    def test_func(self):
        """Only allow superusers to access this view."""
        return self.request.user.is_superuser
    
    def post(self, request, *args, **kwargs):
        """
        Handle POST request to show confirmation before deleting all collections.
        Returns HTML response for HTMX with confirmation dialog.
        """
        stats = CleanupService.get_database_statistics()
        
        # Return HTML for confirmation
        html = render_to_string('blam/dashboard/partials/confirm_delete_collections.html', {
            'stats': stats,
            'action_url': reverse_lazy('database_delete_collections_confirm')
        })
        
        return HttpResponse(html)


class DatabaseDeleteCollectionsConfirmView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View to handle confirming deletion of all collections.
    Only accessible to superusers.
    """
    
    def test_func(self):
        """Only allow superusers to access this view."""
        return self.request.user.is_superuser
    
    def post(self, request, *args, **kwargs):
        """
        Handle POST request to confirm and execute deletion of all collections.
        Returns HTML response for HTMX with deletion results.
        """
        # Run the deletion operation
        results = CleanupService.delete_collections_only()
        
        # Extract counts for a summary message
        deleted = results['deleted']
        orphaned = results['orphaned']
        
        # Prepare success message with summary counts
        message = f"Collections deletion completed. Deleted {deleted['collections']} collections and orphaned {orphaned['bundles']} bundles."
        
        # Check for errors
        errors = results.get('errors', [])
        if errors:
            message += f" Encountered {len(errors)} errors during deletion."
        
        # Return HTML for results
        html = render_to_string('blam/dashboard/partials/delete_results.html', {
            'message': message,
            'deleted': deleted,
            'orphaned': orphaned,
            'errors': errors,
            'operation': 'collections'
        })
        
        return HttpResponse(html)


class DatabaseDeleteBundlesView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View to handle deleting only bundles while keeping collections.
    Only accessible to superusers.
    """
    
    def test_func(self):
        """Only allow superusers to access this view."""
        return self.request.user.is_superuser
    
    def post(self, request, *args, **kwargs):
        """
        Handle POST request to show confirmation before deleting all bundles.
        Returns HTML response for HTMX with confirmation dialog.
        """
        stats = CleanupService.get_database_statistics()
        
        # Return HTML for confirmation
        html = render_to_string('blam/dashboard/partials/confirm_delete_bundles.html', {
            'stats': stats,
            'action_url': reverse_lazy('database_delete_bundles_confirm')
        })
        
        return HttpResponse(html)


class DatabaseDeleteBundlesConfirmView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View to handle confirming deletion of all bundles.
    Only accessible to superusers.
    """
    
    def test_func(self):
        """Only allow superusers to access this view."""
        return self.request.user.is_superuser
    
    def post(self, request, *args, **kwargs):
        """
        Handle POST request to confirm and execute deletion of all bundles.
        Returns HTML response for HTMX with deletion results.
        """
        # Run the deletion operation
        results = CleanupService.delete_bundles_only()
        
        # Extract counts for a summary message
        deleted = results['deleted']
        affected = results['affected']
        
        # Prepare success message with summary counts
        message = f"Bundles deletion completed. Deleted {deleted['bundles']} bundles and {deleted['media_resources'] + deleted['written_resources'] + deleted['other_resources']} resources. Affected {affected['collections']} collections."
        
        # Check for errors
        errors = results.get('errors', [])
        if errors:
            message += f" Encountered {len(errors)} errors during deletion."
        
        # Return HTML for results
        html = render_to_string('blam/dashboard/partials/delete_results.html', {
            'message': message,
            'deleted': deleted,
            'affected': affected,
            'errors': errors,
            'operation': 'bundles'
        })
        
        return HttpResponse(html)


class ArchivistMetadataPanelView(LoginRequiredMixin, UserPassesTestMixin, HtmxTemplateHelperMixin, View):
    """
    HTMX view for the BLAM metadata dashboard panel.
    """

    def test_func(self):
        """Only allow staff users to access this view."""
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        from django.db.models import Q

        kind = request.GET.get("kind", "collections")
        if kind not in {"collections", "bundles"}:
            return self.htmx_error_response("Unknown metadata type.", status=400)

        search_query = request.GET.get("q", "").strip()
        page_number = request.GET.get("page", "1")

        if kind == "collections":
            base_qs = Collection.objects.prefetch_related("general_info").order_by("identifier")
            total_count = base_qs.count()
            if search_query:
                base_qs = base_qs.filter(
                    Q(identifier__icontains=search_query)
                    | Q(general_info__display_title__icontains=search_query)
                    | Q(general_info__description__icontains=search_query)
                ).distinct()
            result_count = base_qs.count()
            paginator = Paginator(base_qs, 50)
            page_obj = paginator.get_page(page_number)
            context = {
                "kind": kind,
                "kind_label": "Collections",
                "collections": page_obj,
                "page_obj": page_obj,
                "search_query": search_query,
                "total_count": total_count,
                "result_count": result_count,
                "editor_target_id": "metadata-editor-modal-content",
            }
        else:
            base_qs = Bundle.objects.prefetch_related("general_info").order_by("identifier")
            total_count = base_qs.count()
            if search_query:
                base_qs = base_qs.filter(
                    Q(identifier__icontains=search_query)
                    | Q(general_info__display_title__icontains=search_query)
                    | Q(general_info__description__icontains=search_query)
                ).distinct()
            result_count = base_qs.count()
            paginator = Paginator(base_qs, 50)
            page_obj = paginator.get_page(page_number)
            context = {
                "kind": kind,
                "kind_label": "Bundles",
                "bundles": page_obj,
                "page_obj": page_obj,
                "search_query": search_query,
                "total_count": total_count,
                "result_count": result_count,
                "editor_target_id": "metadata-editor-modal-content",
            }

        panel_html = render_to_string(
            "blam/dashboard/partials/metadata_panel.html",
            context,
            request=request,
        )
        meta_html = render_to_string(
            "blam/dashboard/partials/metadata_meta.html",
            context,
            request=request,
        )

        if request.headers.get("HX-Request"):
            html = self.build_oob_response(panel_html, {"metadata-meta": meta_html})
            return HttpResponse(html)

        return HttpResponse(panel_html)


class ArchivistDashboardView(HtmxTemplateHelperMixin, LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Archivist dashboard view.
    Shows administration options for archivists.
    """
    template_name = 'blam/dashboard/archivist_control_panel.html'
    
    def test_func(self):
        """Only allow staff users to access this view."""
        return self.request.user.is_staff
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get database statistics
        context['stats'] = CleanupService.get_database_statistics()
        
        # Add any other context data needed for the dashboard
        context['title'] = 'BLAM Control Panel'
        context['dashboard_tasks'] = BackgroundTask.objects.filter(
            task_name__in=[
                "blam_reindex_search_vectors",
                "blam_database_backup",
                "blam_reindex_collections",
            ]
        )[:10]
        
        return context 
