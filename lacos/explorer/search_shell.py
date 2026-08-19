"""Database-free rendering for the public faceted-search landing pages."""

from __future__ import annotations

from django.shortcuts import render

from lacos.explorer.facets import FacetService
from lacos.explorer.public_search.service import is_anonymous_public_search
from lacos.explorer.public_search.service import public_search_unavailable_response
from lacos.explorer.public_search.service import search_public_index
from lacos.explorer.public_search.store import PublicSearchIndexError


class SearchShellMixin:
    """Render search controls from prewarmed cache without evaluating a queryset."""

    search_shell_facet_cache_key: str
    public_search_scope: str
    search_shell_field_definitions = ()
    search_shell_partial_template = "explorer/partials/search_shell_results.html"

    def render_search_shell(self, request):
        public_index = is_anonymous_public_search(request)
        try:
            facets = (
                search_public_index(self.public_search_scope, request.GET).facets
                if public_index
                else FacetService.get_cached_facets(self.search_shell_facet_cache_key)
            )
        except PublicSearchIndexError:
            return public_search_unavailable_response()
        context = {
            self.context_object_name: (),
            "facets": facets,
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
            "public_search_index": public_index,
        }
        template_name = (
            self.search_shell_partial_template
            if request.headers.get("HX-Request")
            else self.template_name
        )
        return render(request, template_name, context)
