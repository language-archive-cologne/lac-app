"""
Data migration to fix S3ResourceLocation bucket mismatches.

This migration updates S3ResourceLocation records to use the correct bucket
from the associated Collection's import_bucket field.

The bug: map_collection_hierarchy() was using production_bucket (lacos-production)
instead of the Collection's import_bucket (e.g., grails-dev).
"""

from django.db import migrations


def fix_s3_resource_location_buckets(apps, schema_editor):
    """
    Fix S3ResourceLocation records to use the correct bucket from Collection.import_bucket.
    """
    S3ResourceLocation = apps.get_model('storage', 'S3ResourceLocation')
    Collection = apps.get_model('blam', 'Collection')
    Bundle = apps.get_model('blam', 'Bundle')
    BundleStructuralInfo = apps.get_model('blam', 'BundleStructuralInfo')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    # Get content types by app_label and model name
    collection_ct = ContentType.objects.filter(app_label='blam', model='collection').first()
    bundle_ct = ContentType.objects.filter(app_label='blam', model='bundle').first()

    if not collection_ct or not bundle_ct:
        print("Skipping bucket fix migration: required ContentType rows not available yet.")
        return

    updated_count = 0
    skipped_count = 0

    # 1. Fix Collection S3ResourceLocations
    for location in S3ResourceLocation.objects.filter(content_type=collection_ct):
        try:
            collection = Collection.objects.get(id=location.object_id)
            if collection.import_bucket and location.s3_bucket != collection.import_bucket:
                old_bucket = location.s3_bucket
                location.s3_bucket = collection.import_bucket
                location.save(update_fields=['s3_bucket'])
                updated_count += 1
                print(f"  Fixed Collection {collection.id}: {old_bucket} -> {collection.import_bucket}")
            else:
                skipped_count += 1
        except Collection.DoesNotExist:
            print(f"  Warning: Collection {location.object_id} not found for S3ResourceLocation {location.id}")

    # 2. Fix Bundle S3ResourceLocations (get bucket from parent collection)
    for location in S3ResourceLocation.objects.filter(content_type=bundle_ct):
        try:
            bundle = Bundle.objects.get(id=location.object_id)
            # Get parent collection via structural_info
            struct_info = BundleStructuralInfo.objects.filter(bundle=bundle).first()
            if struct_info and struct_info.is_member_of_collection_id:
                collection = Collection.objects.get(id=struct_info.is_member_of_collection_id)
                if collection.import_bucket and location.s3_bucket != collection.import_bucket:
                    old_bucket = location.s3_bucket
                    location.s3_bucket = collection.import_bucket
                    location.save(update_fields=['s3_bucket'])
                    updated_count += 1
                    print(f"  Fixed Bundle {bundle.id}: {old_bucket} -> {collection.import_bucket}")
                else:
                    skipped_count += 1
            else:
                print(f"  Warning: Bundle {bundle.id} has no parent collection")
                skipped_count += 1
        except Bundle.DoesNotExist:
            print(f"  Warning: Bundle {location.object_id} not found for S3ResourceLocation {location.id}")
        except Collection.DoesNotExist:
            print(f"  Warning: Parent collection not found for Bundle {location.object_id}")

    # 3. Fix Resource S3ResourceLocations (MediaResource, WrittenResource, OtherResource)
    # These need to traverse: resource -> BundleResources -> Bundle -> Collection
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
        resource_ct = ContentType.objects.filter(app_label='blam', model=model_name).first()
        if not resource_ct:
            print(f"  Skipping {ResourceModel.__name__} records: ContentType not found.")
            continue

        for location in S3ResourceLocation.objects.filter(content_type=resource_ct):
            try:
                resource = ResourceModel.objects.get(id=location.object_id)

                # Find BundleResources that contains this resource via the M2M relation
                bundle_resources = BundleResources.objects.filter(
                    **{relation_name: resource}
                ).first()

                if bundle_resources and bundle_resources.bundle_id:
                    bundle = Bundle.objects.get(id=bundle_resources.bundle_id)
                    struct_info = BundleStructuralInfo.objects.filter(bundle=bundle).first()

                    if struct_info and struct_info.is_member_of_collection_id:
                        collection = Collection.objects.get(id=struct_info.is_member_of_collection_id)

                        if collection.import_bucket and location.s3_bucket != collection.import_bucket:
                            old_bucket = location.s3_bucket
                            location.s3_bucket = collection.import_bucket
                            location.save(update_fields=['s3_bucket'])
                            updated_count += 1
                            print(f"  Fixed {ResourceModel.__name__} {resource.id}: {old_bucket} -> {collection.import_bucket}")
                        else:
                            skipped_count += 1
                    else:
                        skipped_count += 1
                else:
                    skipped_count += 1
            except ResourceModel.DoesNotExist:
                print(f"  Warning: {ResourceModel.__name__} {location.object_id} not found")
            except (Bundle.DoesNotExist, Collection.DoesNotExist) as e:
                print(f"  Warning: Could not find parent for {ResourceModel.__name__} {location.object_id}: {e}")

    print(f"\nMigration complete: {updated_count} records updated, {skipped_count} skipped")


def reverse_migration(apps, schema_editor):
    """
    Reverse migration is a no-op since we don't know what the original bucket was.
    """
    print("Reverse migration is a no-op - bucket values cannot be automatically restored")


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0008_uploadsession_updated_at'),
        ('blam', '0001_initial'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(fix_s3_resource_location_buckets, reverse_migration),
    ]
