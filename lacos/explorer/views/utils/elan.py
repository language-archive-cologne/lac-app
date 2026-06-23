"""ELAN document parsing utilities."""

import logging
from pathlib import Path
from pathlib import PurePosixPath
from typing import Optional
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from botocore.exceptions import ClientError

from .resource import iter_bundle_resources

logger = logging.getLogger(__name__)


def _media_reference_stem(reference: str) -> str:
    """Extract a normalized filename stem from an ELAN media reference."""
    normalized_reference = unquote(reference).replace("\\", "/")
    candidate_name = PurePosixPath(normalized_reference).name
    return Path(candidate_name).stem.lower()


def _resource_file_stem(resource) -> str:
    """Return a normalized resource file stem for audio matching."""
    return Path(getattr(resource, "file_name", "") or "").stem.lower()


def _merge_annotations_by_time(annotations: list[dict]) -> list[dict]:
    """Merge independent tier annotations that share the same time interval."""
    merged_annotations: list[dict] = []
    annotations_by_time: dict[tuple[float, float], dict] = {}

    for annotation in annotations:
        start = annotation.get("start")
        end = annotation.get("end")
        if start is None or end is None:
            merged_annotations.append(annotation)
            continue

        time_key = (start, end)
        merged = annotations_by_time.get(time_key)
        if merged is None:
            annotations_by_time[time_key] = annotation
            merged_annotations.append(annotation)
            continue

        for tier_id, tier_text in annotation.get("tiers", {}).items():
            if not tier_text:
                continue
            existing_text = merged.setdefault("tiers", {}).get(tier_id)
            if existing_text and existing_text != tier_text:
                merged["tiers"][tier_id] = f"{existing_text}\n{tier_text}"
            else:
                merged["tiers"][tier_id] = tier_text

    return merged_annotations


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
        return {"annotations": [], "media_files": [], "tier_headers": []}
    except Exception:
        logger.exception(
            "Unexpected error fetching ELAN document %s from bucket %s",
            object_key,
            bucket_name,
        )
        return {"annotations": [], "media_files": [], "tier_headers": []}

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
    for header in root.findall("./HEADER"):
        media_file = header.attrib.get("MEDIA_FILE")
        if media_file:
            media_files.append(media_file.strip())

        for descriptor in header.findall("MEDIA_DESCRIPTOR"):
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

    annotations = _merge_annotations_by_time(list(annotations_map.values()))

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
    referenced_stems = {
        stem
        for candidate in elan_data.get("media_files", [])
        if candidate and (stem := _media_reference_stem(candidate))
    }

    target_file_name = getattr(target_resource, "file_name", None)
    fallback_stem = Path(target_file_name).stem.lower() if target_file_name else ""
    if not referenced_stems and not fallback_stem:
        return None

    target_resource_key = (
        target_resource.__class__,
        getattr(target_resource, "id", None),
    )
    audio_resources: list[object] = []

    for resource in iter_bundle_resources(bundle):
        resource_key = (resource.__class__, getattr(resource, "id", None))
        if resource_key == target_resource_key:
            continue
        mime = getattr(resource, "mime_type", "") or ""
        lowered_mime = mime.lower()
        if not lowered_mime.startswith("audio/"):
            continue

        audio_resources.append(resource)

    def sorted_matches(stems: set[str]) -> list[object]:
        return sorted(
            [
                resource
                for resource in audio_resources
                if _resource_file_stem(resource) in stems
            ],
            key=lambda resource: (
                _resource_file_stem(resource),
                getattr(resource, "file_name", "") or "",
            ),
        )

    if referenced_stems:
        matches = sorted_matches(referenced_stems)
        return matches[0] if matches else None

    exact_matches = sorted_matches({fallback_stem})
    if exact_matches:
        return exact_matches[0]

    prefix_matches = sorted(
        [
            resource
            for resource in audio_resources
            if _resource_file_stem(resource).startswith(f"{fallback_stem}_")
        ],
        key=lambda resource: (
            _resource_file_stem(resource),
            getattr(resource, "file_name", "") or "",
        ),
    )

    return prefix_matches[0] if prefix_matches else None
