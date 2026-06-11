"""Collection BLAM export must populate ResourceProxyList.

Regression for issue #145 (note 661796) / #144: collections without member
bundles shipped an empty <ResourceProxyList/>, so the CLARIN VLO would skip
them (it requires at least one ResourceProxy). The exporter must emit one
Metadata proxy per member bundle plus a LandingPage proxy to the collection's
own handle, so every collection exposes at least one proxy.
"""
import pytest

from lacos.blam.mappers.collection.write import CollectionExporter
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from xml.etree import ElementTree as ET


def _ln(tag):
    return tag.rsplit("}", 1)[-1]


def _proxies(xml):
    """Return [(ResourceType, ResourceRef)] for every ResourceProxy, ns-agnostic."""
    out = []
    for el in ET.fromstring(xml).iter():
        if _ln(el.tag) == "ResourceProxy":
            rt = ref = None
            for ch in el:
                if _ln(ch.tag) == "ResourceType":
                    rt = (ch.text or "").strip()
                elif _ln(ch.tag) == "ResourceRef":
                    ref = (ch.text or "").strip()
            out.append((rt, ref))
    return out


@pytest.mark.django_db
def test_collection_export_emits_one_metadata_proxy_per_bundle():
    collection = Collection.objects.create(identifier="hdl:test/coll-rp-001")
    for suffix in ("aaa", "bbb"):
        bundle = Bundle.objects.create(identifier=f"hdl:test/coll-bundle-{suffix}")
        BundleStructuralInfo.objects.create(
            bundle=bundle, is_member_of_collection=collection,
        )

    proxies = _proxies(CollectionExporter().export(collection))
    metadata_refs = [r for t, r in proxies if t == "Metadata"]

    assert "hdl:test/coll-bundle-aaa" in metadata_refs
    assert "hdl:test/coll-bundle-bbb" in metadata_refs
    assert len(metadata_refs) == 2


@pytest.mark.django_db
def test_collection_export_includes_landing_page_to_own_handle():
    collection = Collection.objects.create(identifier="hdl:test/coll-rp-002")
    bundle = Bundle.objects.create(identifier="hdl:test/coll-bundle-ccc")
    BundleStructuralInfo.objects.create(
        bundle=bundle, is_member_of_collection=collection,
    )

    proxies = _proxies(CollectionExporter().export(collection))
    assert ("LandingPage", "hdl:test/coll-rp-002") in proxies


@pytest.mark.django_db
def test_collection_without_bundles_still_exposes_a_proxy():
    """VLO needs at least one ResourceProxy; an empty collection still gets a LandingPage."""
    collection = Collection.objects.create(identifier="hdl:test/coll-rp-empty")

    proxies = _proxies(CollectionExporter().export(collection))
    assert proxies, "collection must expose at least one ResourceProxy"
    assert ("LandingPage", "hdl:test/coll-rp-empty") in proxies
