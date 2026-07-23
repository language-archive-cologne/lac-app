from pathlib import Path

import pytest
from django.test import RequestFactory
from django.urls import reverse

from lacos.common.views import guideline_view


@pytest.mark.django_db
def test_guideline_view_sanitizes_rendered_html(settings, tmp_path: Path):
    html_dir = tmp_path / "guidelines"
    html_dir.mkdir()
    (html_dir / "submission.html").write_text(
        "<h1>Submission</h1><script>alert(1)</script><p>Safe</p>",
        encoding="utf-8",
    )
    settings.GUIDELINES_HTML_DIR = html_dir

    response = guideline_view(
        RequestFactory().get("/user-guides/submission-guidelines/"),
        "submission-guidelines",
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "alert(1)" not in content
    assert "Safe" in content


@pytest.mark.django_db
def test_archiving_slug_serves_guideline_content(settings, tmp_path: Path):
    html_dir = tmp_path / "guidelines"
    html_dir.mkdir()
    (html_dir / "archiving_LAC.html").write_text(
        "<h1>Archiving at the LAC</h1><p>Deposit info</p>",
        encoding="utf-8",
    )
    settings.GUIDELINES_HTML_DIR = html_dir

    response = guideline_view(
        RequestFactory().get("/user-guides/archiving/"),
        "archiving",
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "Archiving at the LAC" in content
    assert "Deposit info" in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("legacy_slug", "target_slug"),
    [
        ("depositing-policy", "archiving"),
        ("depositor-agreement", "licenses"),
    ],
)
def test_legacy_slug_redirects_to_title_aligned_slug(legacy_slug, target_slug):
    response = guideline_view(
        RequestFactory().get(f"/user-guides/{legacy_slug}/"),
        legacy_slug,
    )

    assert response.status_code == 301
    assert response.url == reverse("user-guide", args=[target_slug])


def test_sitemap_lists_only_canonical_guide_slugs():
    from lacos.common.views import GUIDELINE_SLUG_REDIRECTS
    from lacos.sitemaps import USER_GUIDE_SLUGS

    # The sitemap must not advertise slugs that 301-redirect elsewhere.
    assert not (set(USER_GUIDE_SLUGS) & set(GUIDELINE_SLUG_REDIRECTS))


@pytest.mark.django_db
def test_user_guides_index_links_use_title_aligned_slugs(client):
    response = client.get(reverse("user-guides"))
    content = response.content.decode()

    assert response.status_code == 200
    assert reverse("user-guide", args=["archiving"]) in content
    assert reverse("user-guide", args=["licenses"]) in content
    assert reverse("user-guide", args=["depositing-policy"]) not in content
    assert reverse("user-guide", args=["depositor-agreement"]) not in content


def _asset_dir(settings, tmp_path: Path) -> Path:
    html_dir = tmp_path / "guidelines"
    assets = html_dir / "assets"
    assets.mkdir(parents=True)
    settings.GUIDELINES_HTML_DIR = html_dir
    return assets


@pytest.mark.django_db
def test_guideline_asset_view_serves_image(settings, tmp_path: Path, client):
    assets = _asset_dir(settings, tmp_path)
    (assets / "pic.png").write_bytes(b"\x89PNG fake")

    response = client.get("/user-guides/assets/pic.png")

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert b"".join(response.streaming_content) == b"\x89PNG fake"


@pytest.mark.django_db
def test_guideline_asset_view_missing_file_returns_404(settings, tmp_path: Path, client):
    _asset_dir(settings, tmp_path)

    assert client.get("/user-guides/assets/nope.png").status_code == 404


@pytest.mark.django_db
def test_guideline_asset_view_rejects_traversal(settings, tmp_path: Path, client):
    assets = _asset_dir(settings, tmp_path)
    (assets.parent / "user.html").write_text("secret", encoding="utf-8")

    response = client.get("/user-guides/assets/..%2Fuser.html")

    assert response.status_code == 404


@pytest.mark.django_db
def test_guideline_asset_view_rejects_non_image_extension(
    settings, tmp_path: Path, client
):
    assets = _asset_dir(settings, tmp_path)
    (assets / "notes.html").write_text("<script>x</script>", encoding="utf-8")

    assert client.get("/user-guides/assets/notes.html").status_code == 404
