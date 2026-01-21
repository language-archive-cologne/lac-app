from django.db import migrations, models


def update_access_levels(apps, schema_editor):
    ACLPermissions = apps.get_model("storage", "ACLPermissions")
    ACLPermissions.objects.filter(access_level="private").update(access_level="restricted")
    ACLPermissions.objects.filter(access_level="embargo").update(access_level="restricted")
    ACLPermissions.objects.filter(access_level="protected").update(access_level="academic")


class Migration(migrations.Migration):
    dependencies = [
        ("storage", "0012_uploadsession_bucket_name"),
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
                    ("restricted", "Restricted"),
                ],
                default="restricted",
                help_text="Normalised access level inferred from the ACL entries",
                max_length=20,
            ),
        ),
    ]
