from __future__ import annotations

from django.urls import reverse
from django.views.generic import TemplateView

from ..constants import SUPPORTED_METADATA_FORMATS, SUPPORTED_SETS


class OAIPMHOverviewView(TemplateView):
    template_name = "pages/oai_pmh.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        endpoint_path = reverse("oaipmh:endpoint")
        absolute_endpoint = self.request.build_absolute_uri(endpoint_path)

        metadata_formats = [
            {
                "metadata_prefix": entry["metadata_prefix"],
                "schema": entry["schema"],
                "namespace": entry["namespace"],
            }
            for entry in SUPPORTED_METADATA_FORMATS
        ]

        sets = [
            {"spec": spec, "name": name}
            for spec, name in SUPPORTED_SETS.items()
        ]

        def _list_links(verb: str):
            links = []
            for format_entry in metadata_formats:
                format_links = [
                    {
                        "label": set_entry["name"],
                        "href": (
                            f"{endpoint_path}?verb={verb}"
                            f"&metadataPrefix={format_entry['metadata_prefix']}"
                            f"&set={set_entry['spec']}"
                        ),
                    }
                    for set_entry in sets
                ]
                links.append(
                    {
                        "metadata_prefix": format_entry["metadata_prefix"],
                        "links": format_links,
                    }
                )
            return links

        context.update(
            {
                "endpoint_path": endpoint_path,
                "endpoint_url": absolute_endpoint,
                "metadata_formats": metadata_formats,
                "sets": sets,
                "core_verbs": [
                    {
                        "verb": "Identify",
                        "description": "Repository identity information",
                        "href": f"{endpoint_path}?verb=Identify",
                    },
                    {
                        "verb": "ListMetadataFormats",
                        "description": "Metadata formats supported by this endpoint",
                        "href": f"{endpoint_path}?verb=ListMetadataFormats",
                    },
                    {
                        "verb": "ListSets",
                        "description": "Available set filters",
                        "href": f"{endpoint_path}?verb=ListSets",
                    },
                ],
                "list_identifiers_links": _list_links("ListIdentifiers"),
                "list_records_links": _list_links("ListRecords"),
            }
        )
        return context
