from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("blam", "0005_alter_bundle_id_and_more"),
        ("users", "0005_change_acl_uri_to_charfield"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectionManagerAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "collection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="collection_manager_assignments",
                        to="blam.collection",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="collection_manager_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Collection manager assignment",
                "verbose_name_plural": "Collection manager assignments",
                "unique_together": {("user", "collection")},
            },
        ),
    ]
