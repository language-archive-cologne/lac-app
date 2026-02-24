from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.views import View
from django.views.generic import TemplateView
from django.template.loader import render_to_string

from lacos.blam.services.cleanup_service import CleanupService
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.common.mixins import HtmxTemplateHelperMixin
from lacos.storage.models import BackgroundTask


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
