"""
Data migration to fix S3ResourceLocation path mismatches.

This migration updates S3ResourceLocation records to use the correct OCFL paths
from the associated Collection's and Bundle's import_object_key fields.

The bug: map_collection_hierarchy() was using UUID-based paths instead of
the actual OCFL paths from import_object_key.
"""

from django.db import migrations


def extract_ocfl_base_path(import_object_key):
    """
    Extract the base OCFL path from an import_object_key.

    The import_object_key format is:
    - Collection: "{collection_folder}/v1/content/{collection_folder}.xml"
    - Bundle: "{collection_folder}/{bundle_folder}/v1/content/{bundle_folder}.xml"

    Returns:
        The base OCFL path (e.g., "qaqet_child_language/" or "qaqet_child_language/bundle1/")
        or None if the path cannot be extracted
    """
    if not import_object_key:
        return None

    # Find the '/v1/content/' marker and extract everything before it
    v1_marker = '/v1/content/'
    idx = import_object_key.find(v1_marker)
    if idx > 0:
        return import_object_key[:idx] + '/'

    return None


def get_ocfl_resource_base_path(bundle_import_object_key):
    """
    Get the base path for resources within a bundle's OCFL structure.

    Resources are stored at: {bundle_path}/v1/content/Resources/

    Returns:
        The base path for resources (e.g., "qaqet_child_language/bundle1/v1/content/Resources/")
        or None if the path cannot be extracted
    """
    if not bundle_import_object_key:
        return None

    v1_marker = '/v1/content/'
    idx = bundle_import_object_key.find(v1_marker)
    if idx > 0:
        return bundle_import_object_key[:idx] + v1_marker + 'Resources/'

    return None


def fix_s3_resource_location_paths(apps, schema_editor):
    """
    Fix S3ResourceLocation records to use the correct OCFL paths from import_object_key.
    """
    S3ResourceLocation = apps.get_model('storage', 'S3ResourceLocation')
    Collection = apps.get_model('blam', 'Collection')
    Bundle = apps.get_model('blam', 'Bundle')
    BundleStructuralInfo = apps.get_model('blam', 'BundleStructuralInfo')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    # Get content types by app_label and model name
    collection_ct = ContentType.objects.get(app_label='blam', model='collection')
    bundle_ct = ContentType.objects.get(app_label='blam', model='bundle')

    updated_count = 0
    skipped_count = 0

    # 1. Fix Collection S3ResourceLocations
    print("\n  Fixing Collection S3ResourceLocation paths...")
    for location in S3ResourceLocation.objects.filter(content_type=collection_ct):
        try:
            collection = Collection.objects.get(id=location.object_id)
            if collection.import_object_key:
                correct_path = extract_ocfl_base_path(collection.import_object_key)
                if correct_path and location.s3_key != correct_path:
                    old_path = location.s3_key
                    location.s3_key = correct_path
                    location.save(update_fields=['s3_key'])
                    updated_count += 1
                    print(f"    Fixed Collection {collection.id}: {old_path} -> {correct_path}")
                else:
                    skipped_count += 1
            else:
                print(f"    Warning: Collection {collection.id} has no import_object_key")
                skipped_count += 1
        except Collection.DoesNotExist:
            print(f"    Warning: Collection {location.object_id} not found for S3ResourceLocation {location.id}")

    # 2. Fix Bundle S3ResourceLocations
    print("\n  Fixing Bundle S3ResourceLocation paths...")
    for location in S3ResourceLocation.objects.filter(content_type=bundle_ct):
        try:
            bundle = Bundle.objects.get(id=location.object_id)
            if bundle.import_object_key:
                correct_path = extract_ocfl_base_path(bundle.import_object_key)
                if correct_path and location.s3_key != correct_path:
                    old_path = location.s3_key
                    location.s3_key = correct_path
                    location.save(update_fields=['s3_key'])
                    updated_count += 1
                    print(f"    Fixed Bundle {bundle.id}: {old_path} -> {correct_path}")
                else:
                    skipped_count += 1
            else:
                print(f"    Warning: Bundle {bundle.id} has no import_object_key")
                skipped_count += 1
        except Bundle.DoesNotExist:
            print(f"    Warning: Bundle {location.object_id} not found for S3ResourceLocation {location.id}")

    # 3. Fix Resource S3ResourceLocations (MediaResource, WrittenResource, OtherResource)
    print("\n  Fixing Resource S3ResourceLocation paths...")
    MediaResource = apps.get_model('blam', 'MediaResource')
    WrittenResource = apps.get_model('blam', 'WrittenResource')
    OtherResource = apps.get_model('blam', 'OtherResource')
    BundleResources = apps.get_model('blam', 'BundleResources')

    resource_models = [
        (MediaResource, 'bundle_media_resources', 'mediaresource'),
        (WrittenResource, 'bundle_written_resources', 'writtenresource'),
        (OtherResource, 'bundle_other_resources', 'otherresource'),
    ]

    for ResourceModel, relation_name, model_name in resource_models:
        resource_ct = ContentType.objects.get(app_label='blam', model=model_name)

        for location in S3ResourceLocation.objects.filter(content_type=resource_ct):
            try:
                resource = ResourceModel.objects.get(id=location.object_id)

                # Find BundleResources that contains this resource via the M2M relation
                bundle_resources = BundleResources.objects.filter(
                    **{relation_name: resource}
                ).first()

                if bundle_resources and bundle_resources.bundle_id:
                    bundle = Bundle.objects.get(id=bundle_resources.bundle_id)

                    if bundle.import_object_key:
                        resources_base_path = get_ocfl_resource_base_path(bundle.import_object_key)

                        if resources_base_path and hasattr(resource, 'file_name') and resource.file_name:
                            correct_path = f"{resources_base_path}{resource.file_name}"
                            if location.s3_key != correct_path:
                                old_path = location.s3_key
                                location.s3_key = correct_path
                                location.save(update_fields=['s3_key'])
                                updated_count += 1
                                print(f"    Fixed {ResourceModel.__name__} {resource.id}: {old_path} -> {correct_path}")
                            else:
                                skipped_count += 1
                        else:
                            skipped_count += 1
                    else:
                        skipped_count += 1
                else:
                    skipped_count += 1
            except ResourceModel.DoesNotExist:
                print(f"    Warning: {ResourceModel.__name__} {location.object_id} not found")
            except (Bundle.DoesNotExist, Collection.DoesNotExist) as e:
                print(f"    Warning: Could not find parent for {ResourceModel.__name__} {location.object_id}: {e}")

    print(f"\n  Migration complete: {updated_count} records updated, {skipped_count} skipped")


def reverse_migration(apps, schema_editor):
    """
    Reverse migration is a no-op since we don't know what the original paths were.
    """
    print("Reverse migration is a no-op - paths cannot be automatically restored")


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0009_fix_s3resourcelocation_buckets'),
        ('blam', '0001_initial'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(fix_s3_resource_location_paths, reverse_migration),
    ]
