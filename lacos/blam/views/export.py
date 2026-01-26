"""Export views for BLAM metadata."""

from django.http import JsonResponse, Http404
from django.views import View

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.serializers import CollectionJsonLdSerializer


class CollectionJsonLdExportView(View):
    """Export a collection's metadata as JSON-LD."""

    def get(self, request, collection_id):
        try:
            collection = Collection.objects.prefetch_related(
                "header",
                "general_info",
                "general_info__keywords",
                "general_info__object_languages",
                "general_info__object_languages__alternative_names",
                "general_info__object_languages__taxonomy",
                "general_info__object_languages__taxonomy__language_family",
                "general_info__location",
                "publication_info",
                "publication_info__creators",
                "publication_info__contributors",
                "administrative_info",
                "administrative_info__licenses",
                "administrative_info__rights_holders",
                "administrative_info__rights_holders__rights_holder_identifiers",
                "administrative_info__is_identical_to",
                "structural_info",
                "structural_info__additional_metadata_files",
                "project_infos",
                "project_infos__funder_infos",
                "project_infos__funder_infos__funder_identifiers",
                "bundle_collection",
                "bundle_collection__bundle",
                "bundle_collection__bundle__general_info",
            ).get(id=collection_id)
        except Collection.DoesNotExist:
            raise Http404("Collection not found")

        serializer = CollectionJsonLdSerializer(collection)
        data = serializer.serialize()

        # Get filename from collection title or ID
        general_info = collection.general_info.first()
        if general_info and general_info.display_title:
            filename = general_info.display_title.replace(" ", "_")[:50]
        else:
            filename = str(collection_id)[:8]

        response = JsonResponse(data, json_dumps_params={"indent": 2, "ensure_ascii": False})
        response["Content-Type"] = "application/ld+json"
        response["Content-Disposition"] = f'attachment; filename="{filename}.jsonld"'
        return response
