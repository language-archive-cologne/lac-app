import pytest
from django.urls import reverse

from lacos.blam.models.collection.collection_publication_info import CollectionCreator


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
