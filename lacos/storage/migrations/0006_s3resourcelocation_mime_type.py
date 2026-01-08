# Generated manually for storage_fix_plan

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0005_aclconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='s3resourcelocation',
            name='mime_type',
            field=models.CharField(
                blank=True,
                help_text='MIME type of the resource (e.g., application/pdf)',
                max_length=255,
                null=True
            ),
        ),
    ]
