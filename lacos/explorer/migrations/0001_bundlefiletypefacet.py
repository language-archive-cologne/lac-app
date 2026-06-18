import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("blam", "0019_collectionmember"),
    ]

    operations = [
        migrations.CreateModel(
            name="BundleFileTypeFacet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "file_type",
                    models.CharField(
                        choices=[
                            ("aac", "AAC"),
                            ("aif", "AIF"),
                            ("aiff", "AIFF"),
                            ("avi", "AVI"),
                            ("cha", "CHAT"),
                            ("cmdi", "CMDI"),
                            ("csv", "CSV"),
                            ("doc", "DOC"),
                            ("docx", "DOCX"),
                            ("eaf", "ELAN"),
                            ("flac", "FLAC"),
                            ("imdi", "IMDI"),
                            ("jpeg", "JPEG"),
                            ("jpg", "JPG"),
                            ("json", "JSON"),
                            ("jsonld", "JSON-LD"),
                            ("m4a", "M4A"),
                            ("mkv", "MKV"),
                            ("mov", "MOV"),
                            ("mp3", "MP3"),
                            ("mp4", "MP4"),
                            ("odt", "ODT"),
                            ("ogg", "OGG"),
                            ("pdf", "PDF"),
                            ("png", "PNG"),
                            ("rtf", "RTF"),
                            ("srt", "SRT subtitles"),
                            ("textgrid", "TextGrid"),
                            ("trs", "Transcriber"),
                            ("tsv", "TSV"),
                            ("txt", "TXT"),
                            ("vtt", "WebVTT subtitles"),
                            ("wav", "WAV"),
                            ("webm", "WebM"),
                            ("xml", "XML"),
                            ("yaml", "YAML"),
                            ("yml", "YML"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "bundle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="file_type_facets",
                        to="blam.bundle",
                    ),
                ),
                (
                    "collection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bundle_file_type_facets",
                        to="blam.collection",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="bundlefiletypefacet",
            constraint=models.UniqueConstraint(
                fields=("bundle", "collection", "file_type"),
                name="unique_bundle_collection_file_type",
            ),
        ),
        migrations.AddIndex(
            model_name="bundlefiletypefacet",
            index=models.Index(
                fields=["file_type", "bundle"],
                name="explorer_ftype_bundle_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="bundlefiletypefacet",
            index=models.Index(
                fields=["file_type", "collection"],
                name="explorer_ftype_collection_idx",
            ),
        ),
    ]
