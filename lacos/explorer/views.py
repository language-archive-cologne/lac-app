import logging
from django.views.generic import DetailView, ListView
from geopy.geocoders import Nominatim
from django.core.cache import cache
from functools import lru_cache
import re

# Assuming your Collection model is here. Adjust if necessary.
from lacos.blam.models import Collection

# Get an instance of a logger
logger = logging.getLogger(__name__)


def get_formatted_location(location):
    """
    Get formatted location string from location object.
    Falls back to different fields in order of preference.
    """
    if location:
        if location.location_name:
            return location.location_name
        elif location.region_name:
            return location.region_name
        elif location.country_name:
            return location.country_name
        elif location.geo_location:
            # If we only have coordinates, try to get location name from reverse geocoding
            return get_location_from_coordinates(location.geo_location)
    return ""


# Cache results to avoid repeated API calls
@lru_cache(maxsize=128)
def get_location_from_coordinates(coordinates):
    """
    Get location name from coordinates using Nominatim (OpenStreetMap).
    Coordinates should be in format "LATITUDE,LONGITUDE" like "50.926735,6.930392"
    """
    try:
        # Create a safe cache key by removing spaces and non-alphanumeric characters
        safe_coordinates = re.sub(r'[^\w\-]', '_', coordinates)
        cache_key = f"geo_location_{safe_coordinates}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        if not coordinates or ',' not in coordinates:
            return coordinates
            
        lat, lng = coordinates.split(',')
        lat = lat.strip()
        lng = lng.strip()
        
        # Just return the coordinates for now to avoid API calls
        # This prevents rate limiting while you're developing
        formatted_coords = f"{lat}, {lng}"
        
        # Store in cache for future use
        cache.set(cache_key, formatted_coords, timeout=60*60*24*30)  # Cache for 30 days
        
        return formatted_coords
        
        # DISABLED GEOCODING TO PREVENT RATE LIMITING
        # Uncomment below for production use
        
        # # Initialize the geocoder with a longer timeout
        # geolocator = Nominatim(user_agent="lacos_app", timeout=10)
        
        # # Reverse geocode
        # location = geolocator.reverse((lat, lng), language='en')
        
        # if location and location.address:
        #     # Get a shorter version of the address if possible
        #     address_parts = location.raw.get('address', {})
        #     if 'city' in address_parts and 'country' in address_parts:
        #         result = f"{address_parts['city']}, {address_parts['country']}"
        #     elif 'town' in address_parts and 'country' in address_parts:
        #         result = f"{address_parts['town']}, {address_parts['country']}"
        #     elif 'village' in address_parts and 'country' in address_parts:
        #         result = f"{address_parts['village']}, {address_parts['country']}"
        #     else:
        #         # Fall back to the full address (might be long)
        #         result = location.address
                
        #     # Store in cache for future use
        #     cache.set(cache_key, result, timeout=60*60*24*30)  # Cache for 30 days
        #     return result
        
        # return coordinates
    except Exception as e:
        logger.error(f"Error fetching location from coordinates: {e}")
        return coordinates


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
        
    def get_context_data(self, **kwargs):
        """Add processed location data to the context."""
        context = super().get_context_data(**kwargs)
        # Process locations for each collection
        collections_with_locations = []
        for collection in context['collection_list']:
            if collection.get_general_info and collection.get_general_info.location:
                location = collection.get_general_info.location
                collection.formatted_location = get_formatted_location(location)
            else:
                collection.formatted_location = ""
            collections_with_locations.append(collection)
        
        context['collection_list'] = collections_with_locations
        return context


class CollectionDetailView(DetailView):
    model = Collection
    # The template name is deduced by default as: 'blam/collection_detail.html'
    # Since our template is directly under 'lacos/lacos/explorer/templates/',
    # we specify the template name explicitly.
    template_name = "collection_detail.html"
    context_object_name = "collection"  # To match the template variable

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add formatted location to the collection
        if self.object.get_general_info and self.object.get_general_info.location:
            location = self.object.get_general_info.location
            self.object.formatted_location = get_formatted_location(location)
        else:
            self.object.formatted_location = ""
        return context

    # If you need to pass bundles separately:
    # def get_context_data(self, **kwargs):
    #     context = super().get_context_data(**kwargs)
    #     context["bundle_list"] = self.object.bundles.all() # Adjust bundle relation if needed
    #     return context 