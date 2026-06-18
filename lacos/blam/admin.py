from django.contrib import admin

# Import Bundle models
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_header import BundleHeader
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo, BundleResources, MediaResource, WrittenResource, OtherResource

# Import Collection models
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo, CollectionMember

# --- Basic Admin Views ---

# Bundle Admin Views
@admin.register(BundleHeader)
class BundleHeaderAdmin(admin.ModelAdmin):
    list_display = ('id', 'md_self_link', 'md_creator', 'md_creation_date')
    search_fields = ('md_self_link', 'md_creator')

@admin.register(BundleGeneralInfo)
class BundleGeneralInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'display_title', 'version')
    search_fields = ('display_title', 'id_value')

@admin.register(BundlePublicationInfo)
class BundlePublicationInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'publication_year', 'data_provider')
    search_fields = ('data_provider',)

@admin.register(BundleAdministrativeInfo)
class BundleAdministrativeInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'access_level', 'availability_date')
    search_fields = ('access_level',)

@admin.register(BundleStructuralInfo)
class BundleStructuralInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_member_of_collection') # Display related collection
    raw_id_fields = ('is_member_of_collection',) 

@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ('id', 'identifier')


# Collection Admin Views
@admin.register(CollectionHeader)
class CollectionHeaderAdmin(admin.ModelAdmin):
    list_display = ('id', 'md_self_link', 'md_creator', 'md_creation_date')
    search_fields = ('md_self_link', 'md_creator')

@admin.register(CollectionGeneralInfo)
class CollectionGeneralInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'display_title', 'version', 'id_value', 'id_type')
    search_fields = ('display_title', 'id_value')
    list_editable = ('id_type',)

@admin.register(CollectionPublicationInfo)
class CollectionPublicationInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'publication_year', 'data_provider')
    search_fields = ('data_provider',)

@admin.register(CollectionAdministrativeInfo)
class CollectionAdministrativeInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'access_level', 'availability_date')
    search_fields = ('access_level',)

@admin.register(CollectionStructuralInfo)
class CollectionStructuralInfoAdmin(admin.ModelAdmin):
    list_display = ('id',)
    # Add fields if needed

@admin.register(CollectionMember)
class CollectionMemberAdmin(admin.ModelAdmin):
    list_display = ('identifier_value', 'identifier_type', 'structural_info')
    search_fields = ('identifier_value',)
    list_filter = ('identifier_type',)

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'identifier')
    search_fields = ('general_info__display_title', 'header__md_self_link', 'general_info__id_value')

# --- Resource Admin Views ---

@admin.register(MediaResource)
class MediaResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'file_name', 'mime_type', 'file_pid', 'file_length')
    search_fields = ('file_name', 'file_pid')
    list_filter = ('mime_type',)

@admin.register(WrittenResource)
class WrittenResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'file_name', 'mime_type', 'file_pid')
    search_fields = ('file_name', 'file_pid')
    list_filter = ('mime_type',)

@admin.register(OtherResource)
class OtherResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'file_name', 'mime_type', 'file_pid')
    search_fields = ('file_name', 'file_pid')
    list_filter = ('mime_type',)

@admin.register(BundleResources)
class BundleResourcesAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_structural_info_pk', 'media_count', 'written_count', 'other_count')
    filter_horizontal = ('bundle_media_resources', 'bundle_written_resources', 'bundle_other_resources') # Better UI for ManyToMany
    readonly_fields = ('get_structural_info_pk',)

    @admin.display(description='Structural Info PK')
    def get_structural_info_pk(self, obj):
        # Access the related BundleStructuralInfo via the related_name
        try:
            # Assuming the related_name on BundleStructuralInfo.resources is 'structural_info'
            return obj.structural_info.pk 
        except BundleStructuralInfo.DoesNotExist: 
            # This case might not happen with OneToOne if the relation is required,
            # but good practice if it could be null temporarily.
            return 'N/A (No Struct Info)'
        except AttributeError:
             # Handle case where the related object might not exist yet or is None
             return 'N/A (Attribute Error)'

    @admin.display(description='Media Count')
    def media_count(self, obj):
        return obj.bundle_media_resources.count()

    @admin.display(description='Written Count')
    def written_count(self, obj):
        return obj.bundle_written_resources.count()

    @admin.display(description='Other Count')
    def other_count(self, obj):
        return obj.bundle_other_resources.count()
