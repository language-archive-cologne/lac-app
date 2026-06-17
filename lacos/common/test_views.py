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
