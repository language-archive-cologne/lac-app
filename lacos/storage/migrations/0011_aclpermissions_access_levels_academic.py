from django.db import migrations, models


def update_access_levels(apps, schema_editor):
    ACLPermissions = apps.get_model("storage", "ACLPermissions")
    ACLPermissions.objects.filter(access_level="protected").update(access_level="academic")
    ACLPermissions.objects.filter(access_level="embargo").update(access_level="private")


class Migration(migrations.Migration):
    dependencies = [
        ("storage", "0010_fix_s3resourcelocation_paths"),
    ]

    operations = [
        migrations.RunPython(update_access_levels, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="aclpermissions",
            name="access_level",
            field=models.CharField(
                choices=[
                    ("public", "Public"),
                    ("academic", "Academic"),
                    ("private", "Private"),
                ],
                default="private",
                help_text="Normalised access level inferred from the ACL entries",
                max_length=20,
            ),
        ),
    ]
