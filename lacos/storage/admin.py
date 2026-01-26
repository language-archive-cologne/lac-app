from django.contrib import admin
from django.utils.html import format_html

from .models import S3ResourceLocation, S3FileObject, UploadSession, ACLPermissions


def format_file_size(size_bytes):
    """Format bytes to human readable size."""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}" if unit_index > 0 else f"{int(size)} B"


@admin.register(S3ResourceLocation)
class S3ResourceLocationAdmin(admin.ModelAdmin):
    list_display = ('resource_pid', 's3_bucket', 's3_key', 'content_type', 'object_id')
    search_fields = ('resource_pid', 's3_bucket', 's3_key')
    list_filter = ('s3_bucket',)


@admin.register(S3FileObject)
class S3FileObjectAdmin(admin.ModelAdmin):
    list_display = (
        'file_name',
        'bucket_name',
        'status_badge',
        'formatted_size',
        'content_type',
        'session_link',
        'created_at',
    )
    list_display_links = ('file_name',)
    search_fields = ('file_name', 's3_key', 'bucket_name', 'session__folder_name')
    list_filter = ('status', 'bucket_name', 'content_type', 'created_at')
    readonly_fields = (
        'id',
        'created_at',
        'updated_at',
        'upload_completed_at',
        'formatted_size',
        's3_uri',
    )
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 50
    raw_id_fields = ('session',)

    fieldsets = (
        ('File Info', {
            'fields': ('file_name', 'original_path', 'content_type', 'formatted_size')
        }),
        ('S3 Location', {
            'fields': ('bucket_name', 's3_key', 's3_uri')
        }),
        ('Upload Status', {
            'fields': ('status', 'error_message', 'etag', 'session')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at', 'upload_completed_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Size')
    def formatted_size(self, obj):
        return format_file_size(obj.file_size_bytes)

    @admin.display(description='Status')
    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'uploading': '#3b82f6',
            'completed': '#10b981',
            'verified': '#059669',
            'failed': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            color,
            obj.status.upper()
        )

    @admin.display(description='Session')
    def session_link(self, obj):
        if obj.session:
            return format_html(
                '<a href="/admin/storage/uploadsession/{}/change/">{}</a>',
                obj.session.id,
                obj.session.folder_name or str(obj.session.id)[:8]
            )
        return '-'

    @admin.display(description='S3 URI')
    def s3_uri(self, obj):
        if obj.bucket_name and obj.s3_key:
            return f"s3://{obj.bucket_name}/{obj.s3_key}"
        return '-'

@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = (
        'short_id',
        'folder_name',
        'bucket_name',
        'user',
        'status_badge',
        'file_count',
        'formatted_size',
        'created_at',
    )
    search_fields = ('id', 'user__username', 'folder_name', 'bucket_name')
    list_filter = ('status', 'bucket_name', 'created_at')
    readonly_fields = ('id', 'created_at', 'updated_at', 'completed_at', 'formatted_size')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 50
    raw_id_fields = ('user',)

    fieldsets = (
        ('Session Info', {
            'fields': ('id', 'user', 'folder_name', 'bucket_name')
        }),
        ('Status', {
            'fields': ('status', 'total_files', 'formatted_size')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='ID')
    def short_id(self, obj):
        return str(obj.id)[:8]

    @admin.display(description='Status')
    def status_badge(self, obj):
        colors = {
            'initialized': '#6b7280',
            'in_progress': '#3b82f6',
            'completed': '#10b981',
            'failed': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            color,
            obj.status.replace('_', ' ').upper()
        )

    @admin.display(description='Files')
    def file_count(self, obj):
        return obj.total_files

    @admin.display(description='Size')
    def formatted_size(self, obj):
        return format_file_size(obj.total_size_bytes)

@admin.register(ACLPermissions)
class ACLPermissionsAdmin(admin.ModelAdmin):
    list_display = ('id', 'content_type', 'object_id')
    list_filter = ('content_type',)
