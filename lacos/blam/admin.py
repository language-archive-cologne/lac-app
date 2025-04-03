from django.contrib import admin

# Import Bundle models
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_header import BundleHeader
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo

# Import Collection models
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo

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
    list_display = ('id', 'get_display_title', 'get_self_link')
    search_fields = ('general_info__display_title', 'base_header__md_self_link')
    raw_id_fields = ('base_header', 'general_info', 'publication_info', 'administrative_info', 'structural_info')

    @admin.display(description='Display Title')
    def get_display_title(self, obj):
        return obj.general_info.display_title if obj.general_info else 'N/A'

    @admin.display(description='Self Link')
    def get_self_link(self, obj):
        return obj.base_header.md_self_link if obj.base_header else 'N/A'

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

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_display_title', 'get_self_link', 'get_collection_id')
    search_fields = ('general_info__display_title', 'base_header__md_self_link', 'general_info__id_value')
    raw_id_fields = ('base_header', 'general_info', 'publication_info', 'administrative_info', 'structural_info') # Added project_info potentially
    # If ProjectInfo is linked, add it to raw_id_fields: 'project_info'

    @admin.display(description='Display Title')
    def get_display_title(self, obj):
        return obj.general_info.display_title if obj.general_info else 'N/A'

    @admin.display(description='Self Link')
    def get_self_link(self, obj):
        return obj.base_header.md_self_link if obj.base_header else 'N/A'

    @admin.display(description='Collection ID')
    def get_collection_id(self, obj):
        return obj.general_info.id_value if obj.general_info else 'N/A'
