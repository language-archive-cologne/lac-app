"""Sitemap configuration for the Language Archive Cologne."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from lacos.blam.models import Bundle, Collection


class StaticSitemap(Sitemap):
    """Sitemap for static pages."""

    priority = 0.5
    changefreq = "monthly"

    def items(self):
        return [
            "home",
            "about",
            "privacy-policy",
            "imprint",
            "oai-pmh",
            "user-guides",
            "user-guide-mission",
            "user-guide-privacy",
            "user-guide-terms",
            "user-guide-dua",
            "user-guide-depositing",
            "user-guide-depositor",
            "user-guide-agreement",
            "user-guide-submission",
            "user-guide-metadata",
            "user-guide-formats",
            "user-guide-archive",
            "user-guide-preservation",
        ]

    def location(self, item):
        return reverse(item)


class CollectionSitemap(Sitemap):
    """Sitemap for collection pages."""

    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return Collection.objects.all()

    def location(self, obj):
        return reverse(
            "explorer:collection_detail_by_handle", kwargs={"handle": obj.identifier}
        )

    def lastmod(self, obj):
        return obj.updated_at if hasattr(obj, "updated_at") else None


class BundleSitemap(Sitemap):
    """Sitemap for bundle pages."""

    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return Bundle.objects.all()

    def location(self, obj):
        return reverse(
            "explorer:bundle_detail_by_handle", kwargs={"handle": obj.identifier}
        )

    def lastmod(self, obj):
        return obj.updated_at if hasattr(obj, "updated_at") else None


sitemaps = {
    "static": StaticSitemap,
    "collections": CollectionSitemap,
    "bundles": BundleSitemap,
}
