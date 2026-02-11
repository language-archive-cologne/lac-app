"""Add B-tree indexes on columns used for faceted search counting and filtering."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("blam", "0009_alter_bundleobjectlanguage_glottolog_code_and_more"),
    ]

    operations = [
        # CollectionLocation — country / region facets
        migrations.AddIndex(
            model_name="collectionlocation",
            index=models.Index(
                fields=["country_facet"],
                name="coll_loc_country_facet_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="collectionlocation",
            index=models.Index(
                fields=["region_facet"],
                name="coll_loc_region_facet_idx",
            ),
        ),
        # CollectionPublicationInfo — year / provider facets
        migrations.AddIndex(
            model_name="collectionpublicationinfo",
            index=models.Index(
                fields=["publication_year"],
                name="coll_pub_year_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="collectionpublicationinfo",
            index=models.Index(
                fields=["data_provider"],
                name="coll_pub_provider_idx",
            ),
        ),
        # CollectionAdministrativeInfo — access level facet
        migrations.AddIndex(
            model_name="collectionadministrativeinfo",
            index=models.Index(
                fields=["access_level"],
                name="coll_admin_access_idx",
            ),
        ),
        # CollectionLicense — license access facet
        migrations.AddIndex(
            model_name="collectionlicense",
            index=models.Index(
                fields=["access"],
                name="coll_license_access_idx",
            ),
        ),
        # CollectionObjectLanguage — language code facet
        migrations.AddIndex(
            model_name="collectionobjectlanguage",
            index=models.Index(
                fields=["iso_639_3_code"],
                name="coll_lang_iso639_idx",
            ),
        ),
        # CollectionKeyword — keyword value facet
        migrations.AddIndex(
            model_name="collectionkeyword",
            index=models.Index(
                fields=["value"],
                name="coll_keyword_value_idx",
            ),
        ),
    ]
