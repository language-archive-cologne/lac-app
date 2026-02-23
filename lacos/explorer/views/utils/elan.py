"""ELAN document parsing utilities."""

import logging
from pathlib import Path
from typing import Optional
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from botocore.exceptions import ClientError

from .resource import iter_bundle_resources


logger = logging.getLogger(__name__)


def parse_elan_document(resource_service, bucket_name: str, object_key: str) -> dict:
    """Fetch and parse ELAN (.eaf) metadata for annotations and media links."""
    try:
        response = resource_service.s3_client.get_object(
            Bucket=bucket_name,
            Key=object_key,
        )
    except ClientError as exc:
        logger.error(
            "Unable to fetch ELAN document %s from bucket %s: %s",
            object_key,
            bucket_name,
            exc,
        )
        return {"annotations": [], "media_files": []}

    raw_bytes = response.get("Body").read()
    try:
        elan_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        elan_text = raw_bytes.decode("utf-8", errors="replace")

    return parse_elan_text(elan_text)


def parse_elan_text(elan_text: str) -> dict:
    """Parse ELAN XML text and extract annotations and media file references."""
    try:
        root = ET.fromstring(elan_text)
    except ET.ParseError as exc:
        logger.error("Failed to parse ELAN document: %s", exc)
        return {"annotations": [], "media_files": []}

    timeslots: dict[str, Optional[int]] = {}
    for slot in root.findall("./TIME_ORDER/TIME_SLOT"):
        slot_id = slot.attrib.get("TIME_SLOT_ID")
        if not slot_id:
            continue
        time_value = slot.attrib.get("TIME_VALUE")
        try:
            timeslots[slot_id] = int(time_value) if time_value is not None else None
        except ValueError:
            timeslots[slot_id] = None

    media_files: list[str] = []
    for descriptor in root.findall("./HEADER/MEDIA_DESCRIPTOR"):
        relative = descriptor.attrib.get("RELATIVE_MEDIA_URL")
        media_url = relative or descriptor.attrib.get("MEDIA_URL")
        if media_url:
            media_files.append(media_url.strip())

    tier_headers: dict[str, None] = {}
    annotations_map: dict[str, dict] = {}

    def ensure_entry(annotation_id: str) -> dict:
        entry = annotations_map.get(annotation_id)
        if entry is None:
            entry = {
                "id": annotation_id,
                "start": None,
                "end": None,
                "tiers": {},
            }
            annotations_map[annotation_id] = entry
        return entry

    def time_to_seconds(value: Optional[int]) -> Optional[float]:
        if value is None:
            return None
        return (value or 0) / 1000

    # Maps each REF_ANNOTATION's own ID to its ANNOTATION_REF target.
    # Used to resolve multi-level chains (grandchild -> child -> root).
    ref_chain: dict[str, str] = {}
    # Deferred REF_ANNOTATION data: (tier_id, reference_id, value_text).
    # Processed after all tiers so the full reference chain is available.
    deferred_refs: list[tuple[str, str, str]] = []

    for tier in root.findall("TIER"):
        tier_id = tier.attrib.get("TIER_ID", "Tier")
        tier_headers[tier_id] = None

        for annotation in tier.findall("./ANNOTATION"):
            alignable = annotation.find("ALIGNABLE_ANNOTATION")
            ref_annotation = annotation.find("REF_ANNOTATION")

            if alignable is not None:
                annotation_id = alignable.attrib.get("ANNOTATION_ID")
                if not annotation_id:
                    continue

                entry = ensure_entry(annotation_id)

                start_ref = alignable.attrib.get("TIME_SLOT_REF1")
                end_ref = alignable.attrib.get("TIME_SLOT_REF2")
                entry["start"] = time_to_seconds(timeslots.get(start_ref))
                entry["end"] = time_to_seconds(timeslots.get(end_ref))

                value_element = alignable.find("ANNOTATION_VALUE")
                value_text = (
                    value_element.text.strip()
                    if value_element is not None and value_element.text
                    else ""
                )

                if value_text:
                    entry.setdefault("tiers", {})[tier_id] = value_text

            elif ref_annotation is not None:
                ann_id = ref_annotation.attrib.get("ANNOTATION_ID")
                reference_id = ref_annotation.attrib.get("ANNOTATION_REF")
                if not reference_id:
                    continue

                if ann_id:
                    ref_chain[ann_id] = reference_id

                value_element = ref_annotation.find("ANNOTATION_VALUE")
                value_text = (
                    value_element.text.strip()
                    if value_element is not None and value_element.text
                    else ""
                )

                if value_text:
                    deferred_refs.append((tier_id, reference_id, value_text))

    # Resolve multi-level reference chains to the root ALIGNABLE_ANNOTATION.
    def resolve_root(ref_id: str) -> str:
        visited: set[str] = set()
        current = ref_id
        while current in ref_chain and current not in visited:
            visited.add(current)
            current = ref_chain[current]
        return current

    for tier_id, reference_id, value_text in deferred_refs:
        root_id = resolve_root(reference_id)
        entry = ensure_entry(root_id)
        entry.setdefault("tiers", {})[tier_id] = value_text

    annotations = list(annotations_map.values())

    if "Tier" in tier_headers and len(tier_headers) > 1:
        del tier_headers["Tier"]

    tier_list = list(tier_headers)

    for entry in annotations:
        entry['ordered_tiers'] = [
            {
                'name': tier,
                'value': entry.get('tiers', {}).get(tier, ''),
            }
            for tier in tier_list
        ]

    annotations.sort(
        key=lambda item: (
            item["start"] if item["start"] is not None else -1,
            item.get("id", ""),
        )
    )

    for entry in annotations:
        tier_texts = [text for text in entry.get("tiers", {}).values() if text]
        entry["value"] = tier_texts[0] if tier_texts else ""

    return {
        "annotations": annotations,
        "media_files": media_files,
        "tier_headers": tier_list,
    }


def pick_elan_audio_resource(bundle, target_resource, elan_data: dict):
    """Choose the most relevant audio resource for an ELAN file."""
    base_names = {Path(target_resource.file_name).stem.lower()}
    for candidate in elan_data.get("media_files", []):
        if not candidate:
            continue
        candidate_name = Path(unquote(candidate)).name
        base_names.add(Path(candidate_name).stem.lower())

    audio_candidates: list[tuple[int, object]] = []

    for resource in iter_bundle_resources(bundle):
        if resource.id == target_resource.id:
            continue
        mime = getattr(resource, "mime_type", "") or ""
        lowered_mime = mime.lower()
        if not lowered_mime.startswith("audio/"):
            continue

        resource_stem = Path(resource.file_name).stem.lower()
        score = 0
        if resource_stem in base_names:
            score += 2
        if resource_stem == Path(target_resource.file_name).stem.lower():
            score += 1

        if score == 0 and not audio_candidates:
            score = 1

        audio_candidates.append((score, resource))

    if not audio_candidates:
        return None

    audio_candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_resource = audio_candidates[0]
    return best_resource if best_score > 0 else None
