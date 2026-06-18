from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory

GOOGLE_SITE_VERIFICATION_META = (
    '<meta name="google-site-verification" '
    'content="plPEbXXF3klc5LrIY25Ibjq_HMik4XiMP3Kggj7_F0g" />'
)


def test_base_template_includes_google_site_verification_meta():
    request = RequestFactory().get("/about/")
    request.user = AnonymousUser()

    html = render_to_string("pages/about.html", request=request)
    assert GOOGLE_SITE_VERIFICATION_META in html
    assert html.count(GOOGLE_SITE_VERIFICATION_META) == 1
