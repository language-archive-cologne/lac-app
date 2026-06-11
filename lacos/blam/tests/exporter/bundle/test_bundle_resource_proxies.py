"""Bundle BLAM export must populate ResourceProxyList.

Regression for issue #145: bundle OAI BLAM records shipped an empty
<ResourceProxyList/>, so the CLARIN VLO skipped every bundle (it requires at
least one ResourceProxy). The exporter must derive a Resource proxy per file
(from file_pid) plus a LandingPage proxy to the bundle's own handle.
"""
import pytest

from lacos.blam.mappers.bundle.write.bundle_exporter import BundleExporter
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    MediaResource,
    WrittenResource,
)
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
def test_bundle_export_emits_one_resource_proxy_per_file():
    bundle = Bundle.objects.create(identifier="hdl:test/bundle-rp-001")
    res = BundleResources.objects.create(bundle=bundle)
    media = MediaResource.objects.create(
        file_name="rec.wav", file_pid="hdl:test/file-aaa",
        mime_type="audio/wav", file_length="123",
    )
    written = WrittenResource.objects.create(
        file_name="notes.pdf", file_pid="hdl:test/file-bbb",
        mime_type="application/pdf",
    )
    res.bundle_media_resources.add(media)
    res.bundle_written_resources.add(written)

    proxies = _proxies(BundleExporter().export(bundle))
    refs = [r for _, r in proxies]

    resource_refs = [r for t, r in proxies if t == "Resource"]
    assert "hdl:test/file-aaa" in resource_refs
    assert "hdl:test/file-bbb" in resource_refs
    assert len(resource_refs) == 2


@pytest.mark.django_db
def test_bundle_export_includes_landing_page_to_own_handle():
    bundle = Bundle.objects.create(identifier="hdl:test/bundle-rp-002")
    res = BundleResources.objects.create(bundle=bundle)
    res.bundle_media_resources.add(MediaResource.objects.create(
        file_name="a.wav", file_pid="hdl:test/file-ccc",
        mime_type="audio/wav", file_length="1",
    ))

    proxies = _proxies(BundleExporter().export(bundle))
    assert ("LandingPage", "hdl:test/bundle-rp-002") in proxies


@pytest.mark.django_db
def test_bundle_without_files_still_exposes_a_proxy():
    """VLO needs at least one ResourceProxy; an empty bundle still gets a LandingPage."""
    bundle = Bundle.objects.create(identifier="hdl:test/bundle-rp-empty")

    proxies = _proxies(BundleExporter().export(bundle))
    assert proxies, "bundle must expose at least one ResourceProxy"
    assert ("LandingPage", "hdl:test/bundle-rp-empty") in proxies
