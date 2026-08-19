from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("explorer", "0001_bundlefiletypefacet"),
    ]

    operations = [
        migrations.CreateModel(
            name="DiscoveryIndexState",
            fields=[
                (
                    "singleton",
                    models.CharField(
                        default="discovery",
                        editable=False,
                        max_length=32,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("source_revision", models.PositiveBigIntegerField(default=0)),
                (
                    "search_vector_revision",
                    models.PositiveBigIntegerField(default=0),
                ),
                (
                    "public_index_revision",
                    models.PositiveBigIntegerField(default=0),
                ),
                ("facet_cache_revision", models.PositiveBigIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ready", "Ready"),
                            ("pending", "Pending"),
                            ("refreshing", "Refreshing"),
                            ("degraded", "Degraded"),
                        ],
                        default="ready",
                        max_length=16,
                    ),
                ),
                ("dirty_at", models.DateTimeField(blank=True, null=True)),
                ("refresh_started_at", models.DateTimeField(blank=True, null=True)),
                ("refresh_completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "public_index_version",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                ("last_error", models.TextField(blank=True, default="")),
            ],
            options={
                "verbose_name": "Discovery index state",
                "verbose_name_plural": "Discovery index state",
            },
        ),
    ]
