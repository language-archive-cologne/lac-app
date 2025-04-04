from django.contrib import admin
from .models import S3ResourceLocation, S3FileObject, UploadSession, ACLPermissions

@admin.register(S3ResourceLocation)
class S3ResourceLocationAdmin(admin.ModelAdmin):
    list_display = ('resource_pid', 's3_bucket', 's3_key', 'content_type', 'object_id')
    search_fields = ('resource_pid', 's3_bucket', 's3_key')
    list_filter = ('s3_bucket',)

@admin.register(S3FileObject)
class S3FileObjectAdmin(admin.ModelAdmin):
    list_display = ('file_name', 'status', 'content_type', 's3_key', 'file_size_bytes')
    search_fields = ('file_name', 's3_key')
    list_filter = ('status', 'content_type', 'session')
    readonly_fields = ('id', 'created_at', 'updated_at', 'upload_completed_at')

@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'user', 'status')
    search_fields = ('id', 'user__username')
    list_filter = ('status',)

@admin.register(ACLPermissions)
class ACLPermissionsAdmin(admin.ModelAdmin):
    list_display = ('id', 'content_type', 'object_id')
    list_filter = ('content_type',)
