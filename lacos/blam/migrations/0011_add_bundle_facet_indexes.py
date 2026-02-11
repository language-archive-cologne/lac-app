"""Add B-tree indexes on columns used for bundle faceted search counting and filtering."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("blam", "0010_add_facet_indexes"),
    ]

    operations = [
        # BundleLocation — country / region facets
        migrations.AddIndex(
            model_name="bundlelocation",
            index=models.Index(
                fields=["country_facet"],
                name="bndl_loc_country_facet_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="bundlelocation",
            index=models.Index(
                fields=["region_facet"],
                name="bndl_loc_region_facet_idx",
            ),
        ),
        # BundleObjectLanguage — language code facet
        migrations.AddIndex(
            model_name="bundleobjectlanguage",
            index=models.Index(
                fields=["iso_639_3_code"],
                name="bndl_lang_iso639_idx",
            ),
        ),
        # BundleKeyword — keyword value facet
        migrations.AddIndex(
            model_name="bundlekeyword",
            index=models.Index(
                fields=["value"],
                name="bndl_keyword_value_idx",
            ),
        ),
        # BundlePublicationInfo — year / provider facets
        migrations.AddIndex(
            model_name="bundlepublicationinfo",
            index=models.Index(
                fields=["publication_year"],
                name="bndl_pub_year_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="bundlepublicationinfo",
            index=models.Index(
                fields=["data_provider"],
                name="bndl_pub_provider_idx",
            ),
        ),
        # BundleAdministrativeInfo — access level facet
        migrations.AddIndex(
            model_name="bundleadministrativeinfo",
            index=models.Index(
                fields=["access_level"],
                name="bndl_admin_access_idx",
            ),
        ),
        # BundleLicense — license access facet
        migrations.AddIndex(
            model_name="bundlelicense",
            index=models.Index(
                fields=["access"],
                name="bndl_license_access_idx",
            ),
        ),
        # BundleTopic — topic name facet
        migrations.AddIndex(
            model_name="bundletopic",
            index=models.Index(
                fields=["name"],
                name="bndl_topic_name_idx",
            ),
        ),
    ]
