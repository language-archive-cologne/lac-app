from django.db import models
from lacos.blam.models.base_structural_info import AdditionalMetadataFile, StructuralInfo
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices


class BundleStructuralInfo(StructuralInfo):
    """
    Concrete implementation of StructuralInfo for bundles
    """
    is_member_of_collection = models.ForeignKey('Collection', on_delete=models.CASCADE, related_name='bundle_members')
    additional_metadata_files = models.ManyToManyField('BundleAdditionalMetadataFile', blank=True)
    bundle_topics = models.ManyToManyField('BundleTopic', blank=True)
    
    class Meta:
        verbose_name = "Bundle Structural Info"
        verbose_name_plural = "Bundle Structural Info"

class BundleAdditionalMetadataFile(AdditionalMetadataFile):
    """
    Concrete implementation of AdditionalMetadataFile for bundles
    """
    class Meta:
        verbose_name = "Bundle Additional Metadata File"
        verbose_name_plural = "Bundle Additional Metadata Files"


class BundleTopic(models.Model):
    """
    A term that occurs as a BundleKeyword in a subset of bundles and defines 
    a meaningful subsection of the bundle.
    
    """
    name = models.CharField(
        max_length=255,
        null=False,
        help_text="Topic term that defines a meaningful subsection of the bundle"
    )
    
    class Meta:
        verbose_name = "Bundle Topic"
        verbose_name_plural = "Bundle Topics"

    def __str__(self):
        return self.name


class BundleTopics(models.Model):
    """
    Model for managing topics associated with a bundle.
    """
    bundle = models.ForeignKey(
        'Bundle',
        on_delete=models.CASCADE,
        related_name='bundle_topics',
        help_text="Bundle associated with these topics"
    )
    topics = models.ManyToManyField(
        'BundleTopic',
        related_name='bundles',
        help_text="Topics associated with the bundle"
    )

    class Meta:
        verbose_name = "Bundle Topics"
        verbose_name_plural = "Bundle Topics"


class BundleMembers(models.Model):
    """
    The BundleMembers component contains elements referencing the resources of the bundle.
    """
    bundle = models.OneToOneField(
        'Bundle',
        on_delete=models.CASCADE,
        related_name='members',
        help_text="Bundle that contains these members"
    )
    
    class Meta:
        verbose_name = "Bundle Members"
        verbose_name_plural = "Bundle Members"


class BundleHasBundleMember(models.Model):
    """
    References to a resource contained in the bundle. Based on the `hasBundleMember` 
    relationship of the Fedora Relationship Ontology.

    """
    bundle_members = models.ForeignKey(
        'BundleMembers',
        on_delete=models.CASCADE,
        related_name='member_references',
        help_text="Bundle members component this reference belongs to"
    )
    member_uri = models.URLField(
        null=False,
        help_text="URI reference to a resource contained in the bundle"
    )
    identifier_type = models.CharField(
        max_length=10,
        choices=IdentifierTypeChoices.choices,
        null=False,
        help_text="The identifier type used (DOI or Handle)"
    )
    order = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional ordering of the member within the bundle"
    )

    class Meta:
        verbose_name = "Bundle Has Bundle Member"
        verbose_name_plural = "Bundle Has Bundle Members"
        ordering = ['order']


class BundleResources(models.Model):
    """
    The BundleResources component contains metadata about files contained in the bundle.
    """
    bundle_media_resources = models.ManyToManyField('MediaResource', blank=True)
    bundle_written_resources = models.ManyToManyField('WrittenResource', blank=True)
    bundle_other_resources = models.ManyToManyField('OtherResource', blank=True)

    class Meta:
        verbose_name = "Bundle Resources"
        verbose_name_plural = "Bundle Resources"


class MediaResource(models.Model):
    """
    The MediaResource component contains metadata about media files contained in the bundle.
    """

    file_name = models.CharField(
        max_length=255,
        null=False,
        help_text="The name of the file as provided by the depositor"
    )
    file_pid = models.URLField(
        null=False,
        help_text="PID that uniquely identifies the file described by this component"
    )
    mime_type = models.CharField(
        max_length=255,
        null=False,
        help_text="Specification of the mime-type of the resource"
    )
    file_length = models.CharField(
        max_length=255,
        null=False,
        help_text="The length of a media file"
    )
    file_description = models.TextField(
        null=True,
        blank=True,
        help_text="A human readable, file specific description"
    )

    class Meta:
        verbose_name = "Media Resource"
        verbose_name_plural = "Media Resources"


class WrittenResource(models.Model):
    """
    The WrittenResource component contains metadata about annotation files and 
    other character encoded information contained in the bundle.
    """

    file_name = models.CharField(
        max_length=255,
        null=False,
        help_text="The name of the file as provided by the depositor"
    )
    file_pid = models.URLField(
        null=False,
        help_text="PID that uniquely identifies the file described by this component"
    )
    mime_type = models.CharField(
        max_length=255,
        null=False,
        help_text="Specification of the mime-type of the resource"
    )
    file_description = models.TextField(
        null=True,
        blank=True,
        help_text="A human readable, file specific description"
    )

    class Meta:
        verbose_name = "Written Resource"
        verbose_name_plural = "Written Resources"


class WrittenResourceAnnotation(models.Model):
    """
    Represents the IsAnnotationOf relationship for a WrittenResource.
    """
    written_resource = models.ForeignKey(
        'WrittenResource',
        on_delete=models.CASCADE,
        related_name='annotations',
        help_text="Written resource that is an annotation"
    )
    is_annotation_of = models.URLField(
        max_length=255,
        null=False,
        help_text="URI of the resource this is an annotation of"
    )

    class Meta:
        verbose_name = "Written Resource Annotation"
        verbose_name_plural = "Written Resource Annotations"


class OtherResource(models.Model):
    """
    The OtherResource component contains metadata about additional files contained in the bundle
    that are not covered by the BundleAdditionalMetadataFile, MediaResource, and WrittenResource components.
    """

    file_name = models.CharField(
        max_length=255,
        null=False,
        help_text="The name of the file as provided by the depositor"
    )
    file_pid = models.URLField(
        null=False,
        help_text="PID that uniquely identifies the file described by this component"
    )
    mime_type = models.CharField(
        max_length=255,
        null=False,
        help_text="Specification of the mime-type of the resource"
    )
    file_description = models.TextField(
        null=True,
        blank=True,
        help_text="A human readable, file specific description"
    )

    class Meta:
        verbose_name = "Other Resource"
        verbose_name_plural = "Other Resources"