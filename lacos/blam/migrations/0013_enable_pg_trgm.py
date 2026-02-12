import django.contrib.postgres.indexes
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("blam", "0012_update_access_level_choices"),
    ]

    operations = [
        TrigramExtension(),
        migrations.AddIndex(
            model_name="collectiongeneralinfo",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["display_title"],
                name="col_title_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="bundlegeneralinfo",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["display_title"],
                name="bnd_title_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="collection",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["identifier"],
                name="col_ident_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="bundle",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["identifier"],
                name="bnd_ident_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]
