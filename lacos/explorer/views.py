import logging
from django.views.generic import DetailView, ListView, View
from geopy.geocoders import Nominatim
from django.core.cache import cache
from functools import lru_cache
import re
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse, Http404, StreamingHttpResponse
from urllib.parse import unquote

from botocore.exceptions import ClientError

# Assuming your Collection model is here. Adjust if necessary.
from lacos.blam.models import Collection, Bundle

# Get an instance of a logger
logger = logging.getLogger(__name__)


def resolve_existing_bucket(resource_service, bucket_candidates, object_key):
    """Return the first bucket containing the object key, using HEAD for validation."""
    for candidate in [bucket for bucket in bucket_candidates if bucket]:
        try:
            resource_service.s3_client.head_object(Bucket=candidate, Key=object_key)
            return candidate
        except ClientError as error:
            error_code = error.response.get('Error', {}).get('Code')
            if error_code in {'404', 'NoSuchKey', 'NotFound'}:
                continue
            raise
    return None


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
            
        # Get all resources from bundles in this collection
        context['collection_media_resources'] = []
        context['collection_written_resources'] = []
        context['collection_other_resources'] = []
        context['collection_metadata_files'] = []
        
        # Get bundles in this collection
        bundles = Bundle.objects.filter(structural_info__is_member_of_collection=self.object)
        
        # Collect resources from all bundles
        for bundle in bundles:
            if bundle.resources.first():
                resources = bundle.resources.first()
                context['collection_media_resources'].extend(resources.bundle_media_resources.all())
                context['collection_written_resources'].extend(resources.bundle_written_resources.all())
                context['collection_other_resources'].extend(resources.bundle_other_resources.all())
                
            if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
                context['collection_metadata_files'].extend(bundle.structural_info.first().additional_metadata_files.all())
                
        return context


class BundleDetailView(DetailView):
    model = Bundle
    template_name = "bundle_detail.html"
    context_object_name = "bundle"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the collection this bundle belongs to
        if hasattr(self.object, 'structural_info') and self.object.structural_info.first():
            context['collection'] = self.object.structural_info.first().is_member_of_collection
        
        # Add formatted location
        if self.object.get_general_info and self.object.get_general_info.location:
            location = self.object.get_general_info.location
            self.object.formatted_location = get_formatted_location(location)
        else:
            self.object.formatted_location = ""
            
        # Get all resources
        context['media_resources'] = []
        context['written_resources'] = []
        context['other_resources'] = []
        context['metadata_files'] = []
        
        if self.object.resources.first():
            resources = self.object.resources.first()
            context['media_resources'] = resources.bundle_media_resources.all()
            context['written_resources'] = resources.bundle_written_resources.all()
            context['other_resources'] = resources.bundle_other_resources.all()
            
        if hasattr(self.object, 'structural_info') and self.object.structural_info.first():
            context['metadata_files'] = self.object.structural_info.first().additional_metadata_files.all()
            
        return context


class BundleResourcesView(View):
    """View for accessing bundle resources directly or listing them"""
    
    def get(self, request, pk, resource_id=None):
        bundle = get_object_or_404(Bundle, pk=pk)
        collection_for_path = None
        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            collection_for_path = bundle.structural_info.first().is_member_of_collection
        
        # If a specific resource is requested, try to serve it directly
        if resource_id:
            try:
                # URL decode the resource_id since it may contain special characters
                decoded_resource_id = unquote(resource_id)
                
                # Remove the 'ID_' prefix if it exists
                if decoded_resource_id.startswith('ID_'):
                    decoded_resource_id = decoded_resource_id[3:]
                
                from lacos.storage.services.resource_mapping_service import ResourceMappingService

                resource_service = ResourceMappingService()
                location = resource_service.resolve_pid_to_s3(decoded_resource_id)
                if not location:
                    raise ValueError(f"No S3 location found for PID: {decoded_resource_id}")

                fallback_bucket = (
                    getattr(bundle, 'import_bucket', None)
                    or (
                        getattr(collection_for_path, 'import_bucket', None)
                        if collection_for_path
                        else None
                    )
                )

                bucket_candidates = [location.s3_bucket, fallback_bucket, resource_service.production_bucket]
                resolved_bucket = resolve_existing_bucket(resource_service, bucket_candidates, location.s3_key)

                if not resolved_bucket:
                    raise ValueError(
                        f"Resource key not available in candidate buckets: {bucket_candidates}"
                    )

                presigned_url = resource_service.generate_presigned_url(
                    resolved_bucket,
                    location.s3_key,
                )

                return redirect(presigned_url)
                
            except ValueError as e:
                logger.error(f"Resource mapping service error: {e}")
                raise Http404(f"Resource {resource_id} not found or cannot be accessed")
            except Exception as e:
                logger.error(f"Error accessing resource: {e}")
                return HttpResponse(f"Error accessing resource: {str(e)}", status=500)
        
        # If no specific resource is requested, show the resources list view
        context = {
            'bundle': bundle,
            'media_resources': [],
            'written_resources': [],
            'other_resources': [],
            'metadata_files': []
        }
        
        if bundle.resources.first():
            resources = bundle.resources.first()
            context['media_resources'] = resources.bundle_media_resources.all()
            context['written_resources'] = resources.bundle_written_resources.all()
            context['other_resources'] = resources.bundle_other_resources.all()
            
        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            context['collection'] = bundle.structural_info.first().is_member_of_collection
            context['metadata_files'] = bundle.structural_info.first().additional_metadata_files.all()
        
        return render(request, 'bundle_resources.html', context)


class ResourceAccessView(View):
    """View for accessing resources either through direct download or streaming"""
    
    def get(self, request, bundle_id, resource_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        collection_for_path = None
        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            collection_for_path = bundle.structural_info.first().is_member_of_collection
        action = request.GET.get('action', 'download')  # Default to download if no action specified
        
        try:
            # Find the resource by its ID (UUID) first
            from django.contrib.contenttypes.models import ContentType
            from lacos.storage.models.s3_resource_location import S3ResourceLocation
            
            # Get the resource
            resource = None
            resource_pid = None
            mime_type = None
            
            # Check in media resources
            if bundle.resources.first():
                for r in bundle.resources.first().bundle_media_resources.all():
                    if r.id == resource_id:
                        resource = r
                        mime_type = r.mime_type
                        break
                
                if not resource:
                    for r in bundle.resources.first().bundle_written_resources.all():
                        if r.id == resource_id:
                            resource = r
                            mime_type = r.mime_type
                            break
                
                if not resource:
                    for r in bundle.resources.first().bundle_other_resources.all():
                        if r.id == resource_id:
                            resource = r
                            mime_type = r.mime_type
                            break
            
            # Check in metadata files
            if not resource and hasattr(bundle, 'structural_info') and bundle.structural_info.first():
                for r in bundle.structural_info.first().additional_metadata_files.all():
                    if r.id == resource_id:
                        resource = r
                        mime_type = r.mime_type
                        break
            
            if not resource:
                raise Http404(f"Resource with id {resource_id} not found in bundle {bundle_id}")
            
            # Get the PID from the resource
            resource_pid = resource.file_pid

            from lacos.storage.services.resource_mapping_service import ResourceMappingService
            from lacos.storage.services.file_discovery_service import FileDiscoveryService

            resource_service = ResourceMappingService()

            location = resource_service.resolve_pid_to_s3(resource_pid)

            bucket_name = None
            object_key = None

            fallback_bucket = (
                getattr(bundle, 'import_bucket', None)
                or (
                    getattr(collection_for_path, 'import_bucket', None)
                    if collection_for_path
                    else None
                )
            )

            if location:
                bucket_candidates = [location.s3_bucket, fallback_bucket, resource_service.production_bucket]
                object_key = location.s3_key
            else:
                discovery_service = FileDiscoveryService()
                if collection_for_path:
                    try:
                        object_key = discovery_service.form_resource_path(
                            collection_for_path.id,
                            bundle.id,
                            resource.file_name,
                        )
                    except Exception:
                        object_key = None

                bucket_candidates = [fallback_bucket, resource_service.production_bucket]

            if not object_key:
                raise ValueError("Unable to determine S3 key for resource")

            bucket_name = resolve_existing_bucket(resource_service, bucket_candidates, object_key)

            if not bucket_name and location and collection_for_path:
                discovery_service = FileDiscoveryService()
                try:
                    object_key = discovery_service.form_resource_path(
                        collection_for_path.id,
                        bundle.id,
                        resource.file_name,
                    )
                    bucket_candidates = [fallback_bucket, resource_service.production_bucket]
                    bucket_name = resolve_existing_bucket(resource_service, bucket_candidates, object_key)
                except Exception:
                    object_key = None

            if not bucket_name:
                raise ValueError("Unable to determine S3 location for resource")

            presigned_url = resource_service.generate_presigned_url(bucket_name, object_key)
            
            # For direct download, just redirect to the presigned URL
            if action == 'download':
                return redirect(presigned_url)
            
            # For streaming/viewing, handle based on the mime type
            if mime_type and (mime_type.startswith('audio/') or mime_type.startswith('video/')):
                range_header = request.META.get('HTTP_RANGE')

                get_kwargs = {
                    'Bucket': bucket_name,
                    'Key': object_key,
                }

                if range_header:
                    get_kwargs['Range'] = range_header

                try:
                    s3_response = resource_service.s3_client.get_object(**get_kwargs)
                except ClientError as s3_error:
                    logger.error(
                        "Error streaming resource %s from bucket %s: %s",
                        resource_id,
                        bucket_name,
                        s3_error,
                    )
                    return HttpResponse(
                        f"Error streaming resource: {s3_error}",
                        status=500,
                    )

                stream_body = s3_response['Body']

                def stream_generator(chunk_size=8192):
                    try:
                        for chunk in stream_body.iter_chunks(chunk_size=chunk_size):
                            if chunk:
                                yield chunk
                    finally:
                        stream_body.close()

                status_code = s3_response.get('ResponseMetadata', {}).get('HTTPStatusCode', 200)
                streaming_response = StreamingHttpResponse(
                    stream_generator(),
                    content_type=mime_type,
                    status=status_code,
                )

                content_length = s3_response.get('ContentLength')
                if content_length is not None:
                    streaming_response['Content-Length'] = str(content_length)

                content_range = s3_response.get('ContentRange')
                if content_range:
                    streaming_response['Content-Range'] = content_range

                streaming_response['Accept-Ranges'] = 'bytes'

                # Ensure partial content status is correct when range requested
                if range_header and status_code == 200:
                    streaming_response.status_code = 206

                return streaming_response
            
            elif mime_type and (mime_type.startswith('image/') or mime_type == 'application/pdf'):
                # For images and PDFs, redirect to view in browser
                return redirect(presigned_url)
            else:
                # For other file types, default to download
                return redirect(presigned_url)
                
        except ValueError as e:
            logger.error(f"Resource mapping service error: {e}")
            raise Http404(f"Resource {resource_id} not found or cannot be accessed")
        except Exception as e:
            logger.error(f"Error accessing resource: {e}")
            return HttpResponse(f"Error accessing resource: {str(e)}", status=500) 
