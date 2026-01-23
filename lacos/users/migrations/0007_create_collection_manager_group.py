from django.db import migrations


def create_collection_manager_group(apps, schema_editor):
    group_model = apps.get_model("auth", "Group")
    group_model.objects.get_or_create(name="collection_manager")


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("users", "0006_collection_manager_assignment"),
    ]

    operations = [
        migrations.RunPython(create_collection_manager_group, migrations.RunPython.noop),
    ]
