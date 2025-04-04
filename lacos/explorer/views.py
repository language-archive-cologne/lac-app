import logging
from django.views.generic import DetailView, ListView

# Assuming your Collection model is here. Adjust if necessary.
from lacos.blam.models import Collection

# Get an instance of a logger
logger = logging.getLogger(__name__)


class CollectionListView(ListView):
    model = Collection
    # The template name is deduced by default as: 'blam/collection_list.html'
    # Since our template is directly under 'lacos/lacos/explorer/templates/',
    # we specify the template name explicitly.
    template_name = "collection_list.html"
    context_object_name = "collection_list"  # To match the template variable

    def get_queryset(self):
        """Explicitly return all collections and log the count."""
        logger.info("Fetching collections in CollectionListView...")
        queryset = Collection.objects.all()
        collection_count = queryset.count()
        logger.info(f"Found {collection_count} collections.")
        return queryset


class CollectionDetailView(DetailView):
    model = Collection
    # The template name is deduced by default as: 'blam/collection_detail.html'
    # Since our template is directly under 'lacos/lacos/explorer/templates/',
    # we specify the template name explicitly.
    template_name = "collection_detail.html"
    context_object_name = "collection"  # To match the template variable

    # If you need to pass bundles separately:
    # def get_context_data(self, **kwargs):
    #     context = super().get_context_data(**kwargs)
    #     context["bundle_list"] = self.object.bundles.all() # Adjust bundle relation if needed
    #     return context 