from http import HTTPStatus


def test_legacy_upload_routes_are_not_exposed(client):
    response = client.post("/api/s3/upload/batch-urls/")
    assert response.status_code == HTTPStatus.NOT_FOUND
