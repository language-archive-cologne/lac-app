"""Summary of the audio derivative and ELAN link tables for the dashboard."""

from django.db.models import Count
from django.db.models import Max
from django.urls import reverse

from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.storage.models import ElanMediaLink
from lacos.storage.models import MediaDerivativeStatus
from lacos.storage.models.media_derivatives import DerivativeStatus
from lacos.storage.models.media_derivatives import ElanLinkStatus

DERIVATIVE_HELP = {
    DerivativeStatus.WORKS: (
        "The player shows the waveform and the spectrogram, and they line up with "
        "the audio. Checked in the files themselves."
    ),
    DerivativeStatus.BROKEN: (
        "The files exist, but the player cannot show them correctly: a header or "
        "size is wrong, or they do not line up with the audio. The admin shows the "
        "failed check. The audio itself still plays."
    ),
    DerivativeStatus.MISSING: (
        "No waveform or no spectrogram. The player shows only a plain audio bar. "
        "The audio itself still plays."
    ),
    DerivativeStatus.FAILED: (
        "The last attempt to make the files failed. The error is in the admin."
    ),
    DerivativeStatus.SOURCE_MISSING: "The audio file itself is not in storage.",
}

LINK_HELP = {
    ElanLinkStatus.REFERENCED_FOUND: (
        "The ELAN file names an audio file, and the bundle contains it."
    ),
    ElanLinkStatus.NAME_FALLBACK: (
        "The ELAN file names no audio file. The app uses the audio file with the "
        "same name."
    ),
    ElanLinkStatus.REFERENCED_MISSING: (
        "The ELAN file names an audio file that the bundle does not contain. "
        "The transcription has no audio."
    ),
    ElanLinkStatus.NO_AUDIO: (
        "The ELAN file names no audio file, and no audio file has the same name."
    ),
    ElanLinkStatus.AUDIO_NO_LOCATION: (
        "The bundle lists the matching audio file, but it is not in storage."
    ),
    ElanLinkStatus.ELAN_UNREADABLE: (
        "The ELAN file is not in storage or is not valid XML."
    ),
}

# Short column headings for the collection table; the cards show the full labels.
SHORT_LABELS = {
    DerivativeStatus.WORKS: "Works",
    DerivativeStatus.BROKEN: "Broken",
    DerivativeStatus.MISSING: "Missing",
    DerivativeStatus.FAILED: "Failed",
    DerivativeStatus.SOURCE_MISSING: "Audio missing",
    ElanLinkStatus.REFERENCED_FOUND: "By ELAN ref.",
    ElanLinkStatus.NAME_FALLBACK: "By file name",
    ElanLinkStatus.REFERENCED_MISSING: "Not in bundle",
    ElanLinkStatus.NO_AUDIO: "No audio",
    ElanLinkStatus.AUDIO_NO_LOCATION: "Not in storage",
    ElanLinkStatus.ELAN_UNREADABLE: "Unreadable",
}

BADGES = {
    DerivativeStatus.WORKS: "badge-success",
    DerivativeStatus.BROKEN: "badge-error",
    DerivativeStatus.MISSING: "badge-error",
    DerivativeStatus.FAILED: "badge-error",
    DerivativeStatus.SOURCE_MISSING: "badge-error",
    ElanLinkStatus.REFERENCED_FOUND: "badge-success",
    ElanLinkStatus.NAME_FALLBACK: "badge-info",
    ElanLinkStatus.REFERENCED_MISSING: "badge-warning",
    ElanLinkStatus.NO_AUDIO: "badge-warning",
    ElanLinkStatus.AUDIO_NO_LOCATION: "badge-error",
    ElanLinkStatus.ELAN_UNREADABLE: "badge-error",
}


def _admin_url(model_name: str, **filters) -> str:
    url = reverse(f"admin:storage_{model_name}_changelist")
    query = "&".join(f"{key}={value}" for key, value in filters.items())
    return f"{url}?{query}" if query else url


def _counts_by(queryset, status_field: str) -> dict:
    """Return {collection_id: {status: count}} and the totals under the key None."""
    result: dict = {None: {}}
    rows = queryset.values("collection_id", status_field).annotate(n=Count("id"))
    for row in rows:
        status = row[status_field]
        result.setdefault(row["collection_id"], {})[status] = row["n"]
        result[None][status] = result[None].get(status, 0) + row["n"]
    return result


def _status_cells(
    counts: dict, choices, model_name: str, field: str, collection_id=None
):
    cells = []
    for status in choices:
        filters = {f"{field}__exact": status.value}
        if collection_id is not None:
            filters["collection__id__exact"] = collection_id
        cells.append(
            {
                "status": status.value,
                "label": status.label,
                "count": counts.get(status.value, 0),
                "badge": BADGES[status],
                "url": _admin_url(model_name, **filters),
            }
        )
    return cells


def get_media_status_summary() -> dict:
    derivatives = _counts_by(MediaDerivativeStatus.objects.all(), "status")
    links = _counts_by(ElanMediaLink.objects.all(), "link_status")

    collection_ids = {key for key in [*derivatives, *links] if key is not None}
    titles = dict(
        CollectionGeneralInfo.objects.filter(
            collection_id__in=collection_ids
        ).values_list("collection_id", "display_title")
    )

    collections = []
    for collection_id in collection_ids:
        derivative_counts = derivatives.get(collection_id, {})
        link_counts = links.get(collection_id, {})
        collections.append(
            {
                "title": titles.get(collection_id) or str(collection_id),
                "audio_total": sum(derivative_counts.values()),
                "elan_total": sum(link_counts.values()),
                "derivatives": _status_cells(
                    derivative_counts,
                    DerivativeStatus,
                    "mediaderivativestatus",
                    "status",
                    collection_id,
                ),
                "links": _status_cells(
                    link_counts,
                    ElanLinkStatus,
                    "elanmedialink",
                    "link_status",
                    collection_id,
                ),
            }
        )
    collections.sort(key=lambda row: row["title"].lower())

    derivative_totals = _status_cells(
        derivatives[None],
        DerivativeStatus,
        "mediaderivativestatus",
        "status",
    )
    link_totals = _status_cells(
        links[None], ElanLinkStatus, "elanmedialink", "link_status"
    )
    for cell in derivative_totals:
        cell["help"] = DERIVATIVE_HELP[cell["status"]]
    for cell in link_totals:
        cell["help"] = LINK_HELP[cell["status"]]

    last_checked = [
        MediaDerivativeStatus.objects.aggregate(t=Max("last_checked_at"))["t"],
        ElanMediaLink.objects.aggregate(t=Max("last_checked_at"))["t"],
    ]
    return {
        "derivative_totals": derivative_totals,
        "link_totals": link_totals,
        "audio_total": sum(derivatives[None].values()),
        "elan_total": sum(links[None].values()),
        "collections": collections,
        "last_checked": max((t for t in last_checked if t), default=None),
        "derivative_columns": [SHORT_LABELS[status] for status in DerivativeStatus],
        "link_columns": [SHORT_LABELS[status] for status in ElanLinkStatus],
    }
