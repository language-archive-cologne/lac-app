"""Sitemap configuration for the Language Archive Cologne."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from lacos.blam.models import Bundle, Collection


# Slugs for user guide pages (only pages with MD files in lac-guidelines/texts/)
USER_GUIDE_SLUGS = [
    "user",
    "depositing-policy",
    "submission-guidelines",
    "depositor-agreement",
    "format-whitelist",
]


class StaticSitemap(Sitemap):
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


class CollectionSitemap(Sitemap):
    """Sitemap for collection pages."""

    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return Collection.objects.all()

    def location(self, obj):
        return reverse(
            "explorer:collection_detail_by_handle", kwargs={"handle": obj.handle_path}
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
            "explorer:bundle_detail_by_handle", kwargs={"handle": obj.handle_path}
        )

    def lastmod(self, obj):
        return obj.updated_at if hasattr(obj, "updated_at") else None


sitemaps = {
    "static": StaticSitemap,
    "collections": CollectionSitemap,
    "bundles": BundleSitemap,
}
