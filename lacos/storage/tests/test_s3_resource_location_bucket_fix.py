"""
Tests for verifying and fixing S3ResourceLocation bucket mismatches.

These tests ensure that S3ResourceLocation records correctly reflect the
bucket where collection data actually resides (Collection.import_bucket).
"""

import pytest
from uuid import uuid4
from datetime import date

from django.contrib.contenttypes.models import ContentType

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_header import BundleHeader
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleStructuralInfo,
    BundleResources,
    MediaResource,
)
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.storage.models.s3_resource_location import S3ResourceLocation


@pytest.fixture
@pytest.mark.django_db
def collection_with_import_bucket():
    """Create a collection with import_bucket set to 'grails-dev'."""
    collection = Collection.objects.create(
        identifier=f"test-collection-{uuid4()}",
        import_bucket="grails-dev",
        import_object_key="qaqet_child_language/v1/content/qaqet_child_language.xml",
    )

    CollectionHeader.objects.create(
        collection=collection,
        md_self_link=f"hdl:test/collection-header-{uuid4()}",
        md_creation_date=date.today(),
    )

    location = CollectionLocation.objects.create(
        location_name="Test Location",
        region_name="Test Region",
        country_name="Test Country",
        country_code="XX",
    )

    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{uuid4()}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Test Collection with Import Bucket",
        location=location,
    )

    return collection


@pytest.fixture
@pytest.mark.django_db
def bundle_with_resources(collection_with_import_bucket):
    """Create a bundle with resources linked to the collection."""
    collection = collection_with_import_bucket

    bundle = Bundle.objects.create(
        identifier=f"test-bundle-{uuid4()}",
        import_bucket="grails-dev",
        import_object_key="qaqet_child_language/bundle1/v1/content/bundle1.xml",
    )

    BundleHeader.objects.create(
        bundle=bundle,
        md_self_link=f"hdl:test/bundle-header-{uuid4()}",
    )

    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )

    resources_container = BundleResources.objects.create(bundle=bundle)

    media_resource = MediaResource.objects.create(
        file_name="test.wav",
        mime_type="audio/wav",
        file_pid=f"hdl:test/{uuid4()}",
    )
    resources_container.bundle_media_resources.add(media_resource)

    return {
        "bundle": bundle,
        "media_resource": media_resource,
        "resources_container": resources_container,
    }


@pytest.mark.django_db
class TestS3ResourceLocationBucketDetection:
    """Tests for detecting and fixing S3ResourceLocation bucket mismatches."""

    def test_collection_has_import_bucket(self, collection_with_import_bucket):
        """Verify collection has import_bucket field set correctly."""
        collection = collection_with_import_bucket
        assert collection.import_bucket == "grails-dev"

    def test_detect_mismatched_collection_bucket(self, collection_with_import_bucket):
        """
        Test that we can detect when S3ResourceLocation points to wrong bucket.

        This simulates the bug where map_collection_hierarchy used production_bucket
        instead of collection.import_bucket.
        """
        collection = collection_with_import_bucket
        ct = ContentType.objects.get_for_model(collection)

        # Create S3ResourceLocation with WRONG bucket (simulating the bug)
        wrong_location = S3ResourceLocation.objects.create(
            content_type=ct,
            object_id=collection.id,
            s3_bucket="lacos-production",  # Wrong! Should be grails-dev
            s3_key=f"collections/{collection.id}/",
        )

        # Verify the mismatch exists
        assert wrong_location.s3_bucket != collection.import_bucket
        assert wrong_location.s3_bucket == "lacos-production"
        assert collection.import_bucket == "grails-dev"

    def test_get_correct_bucket_from_collection(self, collection_with_import_bucket):
        """
        Test that we can determine the correct bucket from Collection.import_bucket.
        """
        collection = collection_with_import_bucket
        ct = ContentType.objects.get_for_model(collection)

        # Create S3ResourceLocation with wrong bucket
        location = S3ResourceLocation.objects.create(
            content_type=ct,
            object_id=collection.id,
            s3_bucket="lacos-production",
            s3_key=f"collections/{collection.id}/",
        )

        # Get the correct bucket from the collection
        correct_bucket = collection.import_bucket

        # Verify we can identify the correct bucket
        assert correct_bucket == "grails-dev"
        assert location.s3_bucket != correct_bucket

    def test_fix_collection_bucket_mismatch(self, collection_with_import_bucket):
        """
        Test that we can fix S3ResourceLocation to use correct bucket.
        """
        collection = collection_with_import_bucket
        ct = ContentType.objects.get_for_model(collection)

        # Create S3ResourceLocation with wrong bucket
        location = S3ResourceLocation.objects.create(
            content_type=ct,
            object_id=collection.id,
            s3_bucket="lacos-production",
            s3_key=f"collections/{collection.id}/",
        )

        # Fix the bucket
        if collection.import_bucket and location.s3_bucket != collection.import_bucket:
            location.s3_bucket = collection.import_bucket
            location.save()

        # Verify the fix
        location.refresh_from_db()
        assert location.s3_bucket == "grails-dev"

    def test_fix_bundle_bucket_via_collection(
        self, collection_with_import_bucket, bundle_with_resources
    ):
        """
        Test that bundle S3ResourceLocation can be fixed via collection's import_bucket.
        """
        collection = collection_with_import_bucket
        bundle = bundle_with_resources["bundle"]
        bundle_ct = ContentType.objects.get_for_model(bundle)

        # Create S3ResourceLocation for bundle with wrong bucket
        bundle_location = S3ResourceLocation.objects.create(
            content_type=bundle_ct,
            object_id=bundle.id,
            s3_bucket="lacos-production",
            s3_key=f"collections/{collection.id}/bundles/{bundle.id}/",
        )

        # Get correct bucket from bundle's collection
        struct_info = bundle.structural_info.first()
        parent_collection = struct_info.is_member_of_collection
        correct_bucket = parent_collection.import_bucket

        # Fix the bucket
        bundle_location.s3_bucket = correct_bucket
        bundle_location.save()

        bundle_location.refresh_from_db()
        assert bundle_location.s3_bucket == "grails-dev"

    def test_fix_resource_bucket_via_collection(
        self, collection_with_import_bucket, bundle_with_resources
    ):
        """
        Test that resource S3ResourceLocation can be fixed via collection's import_bucket.
        """
        collection = collection_with_import_bucket
        bundle = bundle_with_resources["bundle"]
        media_resource = bundle_with_resources["media_resource"]
        resource_ct = ContentType.objects.get_for_model(media_resource)

        # Create S3ResourceLocation for resource with wrong bucket
        resource_location = S3ResourceLocation.objects.create(
            content_type=resource_ct,
            object_id=media_resource.id,
            s3_bucket="lacos-production",
            s3_key=f"collections/{collection.id}/bundles/{bundle.id}/resources/{media_resource.file_name}",
            resource_pid=media_resource.file_pid,
        )

        # Get correct bucket by traversing: resource -> bundle -> collection
        bundle_resources = media_resource.bundleresources_set.first()
        parent_bundle = bundle_resources.bundle
        struct_info = parent_bundle.structural_info.first()
        parent_collection = struct_info.is_member_of_collection
        correct_bucket = parent_collection.import_bucket

        # Fix the bucket
        resource_location.s3_bucket = correct_bucket
        resource_location.save()

        resource_location.refresh_from_db()
        assert resource_location.s3_bucket == "grails-dev"

    def test_find_all_mismatched_locations_for_collection(
        self, collection_with_import_bucket, bundle_with_resources
    ):
        """
        Test that we can find all S3ResourceLocation records that need fixing
        for a given collection.
        """
        collection = collection_with_import_bucket
        bundle = bundle_with_resources["bundle"]
        media_resource = bundle_with_resources["media_resource"]

        # Create S3ResourceLocations with wrong bucket
        collection_ct = ContentType.objects.get_for_model(collection)
        bundle_ct = ContentType.objects.get_for_model(bundle)
        resource_ct = ContentType.objects.get_for_model(media_resource)

        S3ResourceLocation.objects.create(
            content_type=collection_ct,
            object_id=collection.id,
            s3_bucket="lacos-production",
            s3_key=f"collections/{collection.id}/",
        )

        S3ResourceLocation.objects.create(
            content_type=bundle_ct,
            object_id=bundle.id,
            s3_bucket="lacos-production",
            s3_key=f"collections/{collection.id}/bundles/{bundle.id}/",
        )

        S3ResourceLocation.objects.create(
            content_type=resource_ct,
            object_id=media_resource.id,
            s3_bucket="lacos-production",
            s3_key=f"collections/{collection.id}/bundles/{bundle.id}/resources/{media_resource.file_name}",
        )

        # Find all locations pointing to wrong bucket
        wrong_bucket_locations = S3ResourceLocation.objects.filter(
            s3_bucket="lacos-production"
        )

        assert wrong_bucket_locations.count() == 3

        # Fix all of them
        correct_bucket = collection.import_bucket
        updated_count = wrong_bucket_locations.update(s3_bucket=correct_bucket)

        assert updated_count == 3

        # Verify all are fixed
        assert S3ResourceLocation.objects.filter(s3_bucket="lacos-production").count() == 0
        assert S3ResourceLocation.objects.filter(s3_bucket="grails-dev").count() == 3
