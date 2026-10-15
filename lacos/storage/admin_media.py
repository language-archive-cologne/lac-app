"""Admin views for audio derivative status and ELAN audio links."""

from django.contrib import admin
from django.contrib import messages

from .media_audit_tasks import recheck_derivatives_task
from .media_audit_tasks import recheck_elan_links_task
from .media_tasks import generate_peaks_task
from .models import ElanMediaLink
from .models import MediaDerivativeStatus


def _enqueue_generation(objects) -> int:
    count = 0
    for bucket, s3_key in objects:
        if bucket and s3_key:
            generate_peaks_task(bucket, s3_key)
            count += 1
    return count


@admin.register(MediaDerivativeStatus)
class MediaDerivativeStatusAdmin(admin.ModelAdmin):
    list_display = (
        "s3_key",
        "bucket",
        "status",
        "collection",
        "format_version",
        "peaks_last_modified",
        "last_checked_at",
    )
    list_filter = ("status", "collection", "bucket")
    search_fields = ("s3_key", "bucket", "last_error")
    list_select_related = ("collection",)
    ordering = ("bucket", "s3_key")
    list_per_page = 100
    readonly_fields = [field.name for field in MediaDerivativeStatus._meta.fields]
    actions = ("regenerate_derivatives", "recheck")

    def has_add_permission(self, request):
        return False

    @admin.action(description="Regenerate derivatives")
    def regenerate_derivatives(self, request, queryset):
        count = _enqueue_generation(queryset.values_list("bucket", "s3_key"))
        self.message_user(
            request,
            f"Queued derivative generation for {count} audio files.",
            messages.SUCCESS,
        )

    @admin.action(description="Re-check")
    def recheck(self, request, queryset):
        ids = [str(pk) for pk in queryset.values_list("id", flat=True)]
        recheck_derivatives_task(ids)
        self.message_user(
            request, f"Queued a re-check of {len(ids)} audio files.", messages.SUCCESS
        )


@admin.register(ElanMediaLink)
class ElanMediaLinkAdmin(admin.ModelAdmin):
    list_display = (
        "elan_file_name",
        "link_status",
        "audio_file_name",
        "derivative_status",
        "collection",
        "bundle",
        "last_checked_at",
    )
    list_filter = ("link_status", "collection", "audio_derivative__status")
    search_fields = ("elan_file_name", "audio_file_name", "elan_s3_key", "audio_s3_key")
    list_select_related = ("collection", "bundle", "audio_derivative")
    ordering = ("elan_file_name",)
    list_per_page = 100
    readonly_fields = [field.name for field in ElanMediaLink._meta.fields]
    actions = ("regenerate_derivatives", "recheck")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Derivatives", ordering="audio_derivative__status")
    def derivative_status(self, obj):
        return obj.audio_derivative.status if obj.audio_derivative else "-"

    @admin.action(description="Regenerate derivatives")
    def regenerate_derivatives(self, request, queryset):
        count = _enqueue_generation(
            queryset.values_list("audio_bucket", "audio_s3_key")
        )
        self.message_user(
            request,
            f"Queued derivative generation for {count} linked audio files.",
            messages.SUCCESS,
        )

    @admin.action(description="Re-check")
    def recheck(self, request, queryset):
        ids = [str(pk) for pk in queryset.values_list("id", flat=True)]
        recheck_elan_links_task(ids)
        self.message_user(
            request, f"Queued a re-check of {len(ids)} ELAN files.", messages.SUCCESS
        )
