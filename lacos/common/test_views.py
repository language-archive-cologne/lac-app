from pathlib import Path

import pytest
from django.test import RequestFactory

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
