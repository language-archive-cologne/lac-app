"""Sitemap configuration for the Language Archive Cologne."""

from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.storage.services.exposure_policy_service import ExposurePolicyService

# Slugs for user guide pages (only pages with MD files in lac-guidelines/texts/).
# Use the title-aligned slugs so the sitemap lists canonical (non-redirecting) URLs.
USER_GUIDE_SLUGS = [
    "user",
    "archiving",
    "submission-guidelines",
    "licenses",
    "format-whitelist",
    "keywords-cheatsheet",
]


class PublicBaseUrlSitemap(Sitemap):
    """Sitemap base class that emits the advertised public origin."""

    def get_protocol(self, protocol=None):
        parsed = urlsplit(settings.PUBLIC_BASE_URL)
        return parsed.scheme or super().get_protocol(protocol)

    def get_domain(self, site=None):
        parsed = urlsplit(settings.PUBLIC_BASE_URL)
        return parsed.netloc or super().get_domain(site)


class StaticSitemap(PublicBaseUrlSitemap):
    """Sitemap for static pages."""

    priority = 0.5
    changefreq = "monthly"

    def items(self):
        # Static pages without parameters
        static_pages = [
            "home",
            "about",
            "privacy-policy",
            "imprint",
            "oai-pmh",
            "user-guides",
        ]
        # User guide pages (as tuples with slug)
        guide_pages = [("user-guide", slug) for slug in USER_GUIDE_SLUGS]
        return static_pages + guide_pages

    def location(self, item):
        if isinstance(item, tuple):
            name, slug = item
            return reverse(name, kwargs={"slug": slug})
        return reverse(item)


class CollectionSitemap(PublicBaseUrlSitemap):
    """Sitemap for collection pages."""

    priority = 0.8
    changefreq = "weekly"
    policy = ExposurePolicyService()
    anonymous_user = ExposurePolicyService.anonymous_user()

    def items(self):
        queryset = self.policy.filter_collection_queryset(
            self.anonymous_user,
            Collection.objects.all(),
            channel="sitemap",
        )
        return [
            collection for collection in queryset
            if self.policy.can_appear_in_sitemap(self.anonymous_user, collection)
        ]

    def location(self, obj):
        return reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": obj.handle_path},
        )

    def lastmod(self, obj):
        return obj.updated_at if hasattr(obj, "updated_at") else None


class BundleSitemap(PublicBaseUrlSitemap):
    """Sitemap for bundle pages."""

    priority = 0.7
    changefreq = "weekly"
    policy = ExposurePolicyService()
    anonymous_user = ExposurePolicyService.anonymous_user()

    def items(self):
        queryset = self.policy.filter_bundle_queryset(
            self.anonymous_user,
            Bundle.objects.all(),
            channel="sitemap",
        )
        return [
            bundle for bundle in queryset
            if self.policy.can_appear_in_sitemap(self.anonymous_user, bundle)
        ]

    def location(self, obj):
        return reverse(
            "explorer:bundle_detail_by_handle",
            kwargs={"handle": obj.handle_path},
        )

    def lastmod(self, obj):
        return obj.updated_at if hasattr(obj, "updated_at") else None


sitemaps = {
    "static": StaticSitemap,
    "collections": CollectionSitemap,
    "bundles": BundleSitemap,
}
