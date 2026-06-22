from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("blam", "0019_collectionmember"),
    ]

    operations = [
        CreateExtension("pg_stat_statements"),
    ]
