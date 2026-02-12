from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blam', '0011_add_bundle_facet_indexes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bundleadministrativeinfo',
            name='access_level',
            field=models.CharField(choices=[('public', 'Public'), ('academic', 'Academic'), ('restricted', 'Restricted')], default='public', help_text='Access level for this resource', max_length=10),
        ),
        migrations.AlterField(
            model_name='collectionadministrativeinfo',
            name='access_level',
            field=models.CharField(choices=[('public', 'Public'), ('academic', 'Academic'), ('restricted', 'Restricted')], default='public', help_text='Access level for this resource', max_length=10),
        ),
    ]
