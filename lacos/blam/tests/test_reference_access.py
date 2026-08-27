import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from lacos.blam.models.collection.collection_publication_info import CollectionCreator
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
    CollectionStructuralInfo,
)
from lacos.users.models import CollectionManagerAssignment


@pytest.mark.django_db
def test_reference_list_requires_login(client):
    response = client.get(
        reverse("blam:metadata_reference_list", kwargs={"reference_slug": "collection-creators"}),
    )

    assert response.status_code == 302


@pytest.mark.django_db
def test_reference_delete_denies_authenticated_non_archivist(client, django_user_model):
    user = django_user_model.objects.create_user("viewer", "viewer@example.com", "pass")
    client.force_login(user)
    creator = CollectionCreator.objects.create(family_name="Viewer", given_name="User")

    response = client.post(
        reverse(
            "blam:metadata_reference_delete",
            kwargs={"reference_slug": "collection-creators", "object_id": creator.pk},
        ),
    )

    assert response.status_code == 403
    assert CollectionCreator.objects.filter(pk=creator.pk).exists()


@pytest.mark.django_db
def test_inline_reference_remove_denies_anonymous_user(client):
    collection = Collection.objects.create(identifier="hdl:test/reference-access")
    structural_info = CollectionStructuralInfo.objects.create(collection=collection)
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="https://example.test/reference-access.xml",
        file_name="reference-access.xml",
        mime_type="application/xml",
        is_metadata_for=collection.identifier,
    )
    structural_info.additional_metadata_files.add(metadata_file)

    response = client.post(
        reverse(
            "blam:collection_structural_reference_remove",
            kwargs={
                "collection_id": collection.pk,
                "reference_slug": "additional-metadata-files",
                "object_id": metadata_file.pk,
            },
        ),
    )

    assert response.status_code == 403
    assert structural_info.additional_metadata_files.filter(
        pk=metadata_file.pk,
    ).exists()


@pytest.mark.django_db
def test_inline_reference_remove_allows_assigned_collection_manager(
    client,
    django_user_model,
):
    collection = Collection.objects.create(identifier="hdl:test/reference-manager")
    structural_info = CollectionStructuralInfo.objects.create(collection=collection)
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="https://example.test/reference-manager.xml",
        file_name="reference-manager.xml",
        mime_type="application/xml",
        is_metadata_for=collection.identifier,
    )
    structural_info.additional_metadata_files.add(metadata_file)
    user = django_user_model.objects.create_user(
        "reference-manager",
        "reference-manager@example.test",
        "pass",
    )
    user.groups.add(Group.objects.get_or_create(name="collection_manager")[0])
    CollectionManagerAssignment.objects.create(user=user, collection=collection)
    client.force_login(user)

    response = client.post(
        reverse(
            "blam:collection_structural_reference_remove",
            kwargs={
                "collection_id": collection.pk,
                "reference_slug": "additional-metadata-files",
                "object_id": metadata_file.pk,
            },
        ),
    )

    assert response.status_code == 200
    assert not structural_info.additional_metadata_files.filter(
        pk=metadata_file.pk,
    ).exists()
