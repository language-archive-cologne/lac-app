"""Database-free rendering for the public faceted-search landing pages."""

from __future__ import annotations

from django.shortcuts import render

from lacos.explorer.facets import FacetService


class SearchShellMixin:
    """Render search controls from prewarmed cache without evaluating a queryset."""

    search_shell_facet_cache_key: str
    search_shell_field_definitions = ()
    search_shell_partial_template = "explorer/partials/search_shell_results.html"

    def render_search_shell(self, request):
        context = {
            self.context_object_name: (),
            "facets": FacetService.get_cached_facets(
                self.search_shell_facet_cache_key,
            ),
            "active_filters": [],
            "has_active_filters": False,
            "search_query": "",
            "current_sort": "name",
            "current_order": "asc",
            "current_params": request.GET.copy(),
            "field_definitions": self.search_shell_field_definitions,
            "active_search_in": [],
            "total_count": 0,
            "total_count_is_lower_bound": False,
            "is_paginated": False,
            "search_shell": True,
        }
        template_name = (
            self.search_shell_partial_template
            if request.headers.get("HX-Request")
            else self.template_name
        )
        return render(request, template_name, context)
