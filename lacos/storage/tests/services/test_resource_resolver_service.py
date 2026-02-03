"""Tests for ResourceResolverService."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
    MediaResource,
    OtherResource,
    WrittenResource,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.services.resource_resolver_service import (
    ResolvedResource,
    ResourceError,
    ResourceResolverService,
)


User = get_user_model()


@pytest.fixture
def collection():
    """Create a test collection."""
    return Collection.objects.create(identifier="test-collection")


@pytest.fixture
def bundle(collection):
    """Create a test bundle linked to a collection."""
    bundle = Bundle.objects.create(identifier="test-bundle")
    BundleStructuralInfo.objects.create(
        bundle=bundle, is_member_of_collection=collection
    )
    return bundle


@pytest.fixture
def bundle_resources(bundle):
    """Create a BundleResources container for the bundle."""
    return BundleResources.objects.create(bundle=bundle)


@pytest.fixture
def media_resource(bundle_resources):
    """Create a test media resource."""
    resource = MediaResource.objects.create(
        file_name="test_video.mp4",
        file_pid="https://hdl.handle.net/12345/test_video",
        mime_type="video/mp4",
        file_length="00:05:30",
    )
    bundle_resources.bundle_media_resources.add(resource)
    return resource


@pytest.fixture
def written_resource(bundle_resources):
    """Create a test written resource."""
    resource = WrittenResource.objects.create(
        file_name="transcript.txt",
        file_pid="https://hdl.handle.net/12345/transcript",
        mime_type="text/plain",
    )
    bundle_resources.bundle_written_resources.add(resource)
    return resource


@pytest.fixture
def other_resource(bundle_resources):
    """Create a test other resource."""
    resource = OtherResource.objects.create(
        file_name="data.json",
        file_pid="https://hdl.handle.net/12345/data",
        mime_type="application/json",
    )
    bundle_resources.bundle_other_resources.add(resource)
    return resource


@pytest.fixture
def s3_location(media_resource):
    """Create an S3 location for the media resource."""
    content_type = ContentType.objects.get_for_model(media_resource)
    return S3ResourceLocation.objects.create(
        content_type=content_type,
        object_id=str(media_resource.id),
        s3_bucket="test-bucket",
        s3_key="collections/test/bundles/test/resources/test_video.mp4",
        size_bytes=1024000,
        resource_pid=media_resource.file_pid,
    )


@pytest.fixture
def user():
    """Create a test user."""
    return User.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def mock_acl_allowed():
    """Mock ACL service to always allow access."""
    with patch(
        "lacos.storage.services.resource_resolver_service.ACLEvaluationService"
    ) as mock:
        mock_instance = MagicMock()
        mock_instance.is_allowed.return_value = True
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_acl_denied():
    """Mock ACL service to always deny access."""
    with patch(
        "lacos.storage.services.resource_resolver_service.ACLEvaluationService"
    ) as mock:
        mock_instance = MagicMock()
        mock_instance.is_allowed.return_value = False
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_presigned_url():
    """Mock presigned URL service."""
    with patch(
        "lacos.storage.services.resource_resolver_service.get_presigned_url_cache_service"
    ) as mock:
        mock_instance = MagicMock()
        mock_instance.get_download_url.return_value = {
            "url": "https://s3.example.com/presigned-url",
            "filename": "test_video.mp4",
            "expires_in": 86400,
            "curl_command": "curl -C - -o test_video.mp4 https://s3.example.com/presigned-url",
        }
        mock.return_value = mock_instance
        yield mock_instance


@pytest.mark.django_db
class TestResourceResolverService:
    """Tests for ResourceResolverService."""

    def test_resolve_valid_resource(
        self,
        bundle,
        bundle_resources,
        media_resource,
        s3_location,
        user,
        mock_acl_allowed,
        mock_presigned_url,
    ):
        """Test resolving a valid resource returns a ResolvedResource."""
        service = ResourceResolverService()

        resolved, errors = service.resolve_resources(
            bundle_id=str(bundle.id),
            resource_ids=[str(media_resource.id)],
            user=user,
        )

        assert len(resolved) == 1
        assert len(errors) == 0

        result = resolved[0]
        assert result.resource_id == str(media_resource.id)
        assert result.bucket == "test-bucket"
        assert result.key == s3_location.s3_key
        assert result.filename == "test_video.mp4"
        assert result.size == 1024000
        assert result.presigned_url == "https://s3.example.com/presigned-url"

    def test_resolve_invalid_resource_id(
        self,
        bundle,
        bundle_resources,
        user,
        mock_acl_allowed,
        mock_presigned_url,
    ):
        """Test resolving an invalid resource ID returns an error."""
        service = ResourceResolverService()
        invalid_id = str(uuid.uuid4())

        resolved, errors = service.resolve_resources(
            bundle_id=str(bundle.id),
            resource_ids=[invalid_id],
            user=user,
        )

        assert len(resolved) == 0
        assert len(errors) == 1

        error = errors[0]
        assert error.resource_id == invalid_id
        assert error.error == "not_in_bundle"
        assert "does not belong to bundle" in error.message

    def test_resolve_resource_not_in_bundle(
        self,
        bundle,
        bundle_resources,
        user,
        mock_acl_allowed,
        mock_presigned_url,
    ):
        """Test resolving a resource that exists but is not in the bundle."""
        # Create a resource not linked to the bundle
        standalone_resource = MediaResource.objects.create(
            file_name="standalone.mp4",
            file_pid="https://hdl.handle.net/12345/standalone",
            mime_type="video/mp4",
            file_length="00:01:00",
        )

        service = ResourceResolverService()

        resolved, errors = service.resolve_resources(
            bundle_id=str(bundle.id),
            resource_ids=[str(standalone_resource.id)],
            user=user,
        )

        assert len(resolved) == 0
        assert len(errors) == 1
        assert errors[0].error == "not_in_bundle"

    def test_acl_denied_returns_error_for_all_resources(
        self,
        bundle,
        bundle_resources,
        media_resource,
        written_resource,
        s3_location,
        user,
        mock_acl_denied,
    ):
        """Test ACL denied returns error for all requested resources."""
        service = ResourceResolverService()

        resolved, errors = service.resolve_resources(
            bundle_id=str(bundle.id),
            resource_ids=[str(media_resource.id), str(written_resource.id)],
            user=user,
        )

        assert len(resolved) == 0
        assert len(errors) == 2

        for error in errors:
            assert error.error == "access_denied"
            assert "Access denied" in error.message

    def test_mixed_valid_invalid_returns_partial_success(
        self,
        bundle,
        bundle_resources,
        media_resource,
        s3_location,
        user,
        mock_acl_allowed,
        mock_presigned_url,
    ):
        """Test resolving a mix of valid and invalid resources."""
        service = ResourceResolverService()
        invalid_id = str(uuid.uuid4())

        resolved, errors = service.resolve_resources(
            bundle_id=str(bundle.id),
            resource_ids=[str(media_resource.id), invalid_id],
            user=user,
        )

        assert len(resolved) == 1
        assert len(errors) == 1

        assert resolved[0].resource_id == str(media_resource.id)
        assert errors[0].resource_id == invalid_id
        assert errors[0].error == "not_in_bundle"

    def test_bundle_not_found_returns_error_for_all_resources(
        self,
        user,
        mock_acl_allowed,
    ):
        """Test non-existent bundle returns error for all resources."""
        service = ResourceResolverService()
        fake_bundle_id = str(uuid.uuid4())
        resource_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        resolved, errors = service.resolve_resources(
            bundle_id=fake_bundle_id,
            resource_ids=resource_ids,
            user=user,
        )

        assert len(resolved) == 0
        assert len(errors) == 2

        for error in errors:
            assert error.error == "bundle_not_found"
            assert fake_bundle_id in error.message

    def test_resource_without_s3_location(
        self,
        bundle,
        bundle_resources,
        media_resource,
        user,
        mock_acl_allowed,
        mock_presigned_url,
    ):
        """Test resource without S3 location returns no_location error."""
        # Note: No s3_location fixture, so no S3ResourceLocation exists
        service = ResourceResolverService()

        resolved, errors = service.resolve_resources(
            bundle_id=str(bundle.id),
            resource_ids=[str(media_resource.id)],
            user=user,
        )

        assert len(resolved) == 0
        assert len(errors) == 1
        assert errors[0].error == "no_location"

    def test_resolve_multiple_resource_types(
        self,
        bundle,
        bundle_resources,
        media_resource,
        written_resource,
        other_resource,
        user,
        mock_acl_allowed,
        mock_presigned_url,
    ):
        """Test resolving different types of resources (media, written, other)."""
        # Create S3 locations for all resources
        for resource in [media_resource, written_resource, other_resource]:
            content_type = ContentType.objects.get_for_model(resource)
            S3ResourceLocation.objects.create(
                content_type=content_type,
                object_id=str(resource.id),
                s3_bucket="test-bucket",
                s3_key=f"test/{resource.file_name}",
                size_bytes=1024,
            )

        service = ResourceResolverService()

        resolved, errors = service.resolve_resources(
            bundle_id=str(bundle.id),
            resource_ids=[
                str(media_resource.id),
                str(written_resource.id),
                str(other_resource.id),
            ],
            user=user,
        )

        assert len(resolved) == 3
        assert len(errors) == 0

        filenames = {r.filename for r in resolved}
        assert filenames == {"test_video.mp4", "transcript.txt", "data.json"}


@pytest.mark.django_db
class TestResolvedResourceDataclass:
    """Tests for ResolvedResource dataclass."""

    def test_resolved_resource_fields(self):
        """Test ResolvedResource has all expected fields."""
        resource = ResolvedResource(
            resource_id="123",
            bucket="my-bucket",
            key="path/to/file.mp4",
            filename="file.mp4",
            size=1024,
            checksum="abc123",
            presigned_url="https://example.com/signed-url",
        )

        assert resource.resource_id == "123"
        assert resource.bucket == "my-bucket"
        assert resource.key == "path/to/file.mp4"
        assert resource.filename == "file.mp4"
        assert resource.size == 1024
        assert resource.checksum == "abc123"
        assert resource.presigned_url == "https://example.com/signed-url"

    def test_resolved_resource_optional_checksum(self):
        """Test ResolvedResource with None checksum."""
        resource = ResolvedResource(
            resource_id="123",
            bucket="my-bucket",
            key="path/to/file.mp4",
            filename="file.mp4",
            size=1024,
            checksum=None,
            presigned_url="https://example.com/signed-url",
        )

        assert resource.checksum is None


@pytest.mark.django_db
class TestResourceErrorDataclass:
    """Tests for ResourceError dataclass."""

    def test_resource_error_fields(self):
        """Test ResourceError has all expected fields."""
        error = ResourceError(
            resource_id="123",
            error="not_found",
            message="Resource not found",
        )

        assert error.resource_id == "123"
        assert error.error == "not_found"
        assert error.message == "Resource not found"
