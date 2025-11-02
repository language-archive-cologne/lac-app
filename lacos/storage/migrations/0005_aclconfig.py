from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storage", "0004_aclpermissions_access_level_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ACLConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enforcement_enabled", models.BooleanField(default=True)),
                ("log_access_attempts", models.BooleanField(default=True)),
                ("default_deny", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "ACL Configuration",
                "verbose_name_plural": "ACL Configuration",
            },
        ),
    ]





