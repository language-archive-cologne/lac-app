import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BackgroundTask',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('task_name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('huey_task_id', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('success', 'Success'), ('failed', 'Failed')], default='queued', max_length=20)),
                ('message', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('result', models.JSONField(blank=True, null=True)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
