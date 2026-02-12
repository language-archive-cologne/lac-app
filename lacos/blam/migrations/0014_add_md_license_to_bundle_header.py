from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blam', '0013_enable_pg_trgm'),
    ]

    operations = [
        migrations.AddField(
            model_name='bundleheader',
            name='md_license',
            field=models.CharField(blank=True, help_text='Metadata document license (MDLicense value)', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='bundleheader',
            name='md_license_uri',
            field=models.URLField(blank=True, help_text='Metadata document license URI (MDLicense URI)', null=True),
        ),
    ]
