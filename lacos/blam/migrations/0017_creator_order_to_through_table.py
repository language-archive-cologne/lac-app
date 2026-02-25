"""Move creator `order` from Creator models to M2M through tables.

The order field lived on CollectionCreator/BundleCreator, but those records
are shared across publications via get_or_create(family_name, given_name).
When one publication set a creator's order it corrupted every other
publication sharing that creator.

This migration:
1. Adds an `order` column to the existing auto-generated M2M tables.
2. Copies each creator's current order into the matching M2M rows.
3. For NULL-order rows, assigns order based on M2M row id (preserves
   insertion order).
4. Drops `order` from CollectionCreator and BundleCreator.
5. Registers the new explicit through models in Django state so they
   match the already-altered tables.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("blam", "0016_remove_bundle_topics"),
    ]

    operations = [
        # ── 1. Add order column to existing auto M2M tables ──────────
        migrations.RunSQL(
            sql="ALTER TABLE blam_collectionpublicationinfo_creators ADD COLUMN \"order\" integer NULL;",
            reverse_sql="ALTER TABLE blam_collectionpublicationinfo_creators DROP COLUMN \"order\";",
        ),
        migrations.RunSQL(
            sql="ALTER TABLE blam_bundlepublicationinfo_creators ADD COLUMN \"order\" integer NULL;",
            reverse_sql="ALTER TABLE blam_bundlepublicationinfo_creators DROP COLUMN \"order\";",
        ),

        # ── 2. Copy order from creator table into the M2M rows ───────
        migrations.RunSQL(
            sql="""
                UPDATE blam_collectionpublicationinfo_creators AS m2m
                   SET "order" = c."order"
                  FROM blam_collectioncreator AS c
                 WHERE m2m.collectioncreator_id = c.id
                   AND c."order" IS NOT NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                UPDATE blam_bundlepublicationinfo_creators AS m2m
                   SET "order" = c."order"
                  FROM blam_bundlecreator AS c
                 WHERE m2m.bundlecreator_id = c.id
                   AND c."order" IS NOT NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        # ── 3. For still-NULL rows, derive order from M2M row id ─────
        #    (preserves original insertion order)
        migrations.RunSQL(
            sql="""
                UPDATE blam_collectionpublicationinfo_creators AS m2m
                   SET "order" = sub.rn - 1
                  FROM (
                      SELECT id,
                             ROW_NUMBER() OVER (
                                 PARTITION BY collectionpublicationinfo_id
                                 ORDER BY id
                             ) AS rn
                        FROM blam_collectionpublicationinfo_creators
                       WHERE "order" IS NULL
                  ) AS sub
                 WHERE m2m.id = sub.id;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                UPDATE blam_bundlepublicationinfo_creators AS m2m
                   SET "order" = sub.rn - 1
                  FROM (
                      SELECT id,
                             ROW_NUMBER() OVER (
                                 PARTITION BY bundlepublicationinfo_id
                                 ORDER BY id
                             ) AS rn
                        FROM blam_bundlepublicationinfo_creators
                       WHERE "order" IS NULL
                  ) AS sub
                 WHERE m2m.id = sub.id;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        # ── 4. Drop order from the creator tables ────────────────────
        migrations.RemoveField(
            model_name="collectioncreator",
            name="order",
        ),
        migrations.RemoveField(
            model_name="bundlecreator",
            name="order",
        ),

        # ── 5. Register the through models in Django state ───────────
        #    The DB tables already exist (auto-generated M2M tables that
        #    we just altered). SeparateDatabaseAndState lets us tell
        #    Django about the explicit through model without touching the
        #    DB again.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="CollectionPublicationInfoCreator",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        (
                            "collectionpublicationinfo",
                            models.ForeignKey(
                                db_column="collectionpublicationinfo_id",
                                on_delete=django.db.models.deletion.CASCADE,
                                to="blam.collectionpublicationinfo",
                            ),
                        ),
                        (
                            "collectioncreator",
                            models.ForeignKey(
                                db_column="collectioncreator_id",
                                on_delete=django.db.models.deletion.CASCADE,
                                to="blam.collectioncreator",
                            ),
                        ),
                        ("order", models.IntegerField(blank=True, null=True)),
                    ],
                    options={
                        "db_table": "blam_collectionpublicationinfo_creators",
                        "ordering": ["order"],
                        "unique_together": {("collectionpublicationinfo", "collectioncreator")},
                    },
                ),
                migrations.CreateModel(
                    name="BundlePublicationInfoCreator",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        (
                            "bundlepublicationinfo",
                            models.ForeignKey(
                                db_column="bundlepublicationinfo_id",
                                on_delete=django.db.models.deletion.CASCADE,
                                to="blam.bundlepublicationinfo",
                            ),
                        ),
                        (
                            "bundlecreator",
                            models.ForeignKey(
                                db_column="bundlecreator_id",
                                on_delete=django.db.models.deletion.CASCADE,
                                to="blam.bundlecreator",
                            ),
                        ),
                        ("order", models.IntegerField(blank=True, null=True)),
                    ],
                    options={
                        "db_table": "blam_bundlepublicationinfo_creators",
                        "ordering": ["order"],
                        "unique_together": {("bundlepublicationinfo", "bundlecreator")},
                    },
                ),
                # Tell Django the M2M now uses the explicit through model
                migrations.AlterField(
                    model_name="collectionpublicationinfo",
                    name="creators",
                    field=models.ManyToManyField(
                        blank=True,
                        through="blam.CollectionPublicationInfoCreator",
                        to="blam.collectioncreator",
                    ),
                ),
                migrations.AlterField(
                    model_name="bundlepublicationinfo",
                    name="creators",
                    field=models.ManyToManyField(
                        blank=True,
                        through="blam.BundlePublicationInfoCreator",
                        to="blam.bundlecreator",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
