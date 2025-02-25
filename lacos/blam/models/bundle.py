from django.db import models
from django.core.validators import RegexValidator

class AccessChoices(models.TextChoices):
    OPEN = 'open', 'Open'
    REGISTRATION_REQUIRED = 'registration required', 'Registration Required'
    REQUEST_REQUIRED = 'request required', 'Request Required'

class IdentifierTypeChoices(models.TextChoices):
    DOI = 'DOI', 'DOI'
    HANDLE = 'Handle', 'Handle'
    URN = 'URN', 'URN'
    OTHER = 'Other', 'Other'

class BundleCollectionIdentifierTypeChoices(models.TextChoices):
    DOI = 'DOI', 'DOI'
    HANDLE = 'Handle', 'Handle'

class NameIdentifierTypeChoices(models.TextChoices):
    ORCID = 'ORCID', 'ORCID'
    ISNI = 'ISNI', 'ISNI'
    EMAIL = 'Email', 'Email'
    OTHER = 'Other', 'Other'

class FunderIdentifierTypeChoices(models.TextChoices):
    CROSSREF_FUNDER = 'CrossrefFunder', 'Crossref Funder'
    ISNI = 'ISNI', 'ISNI'
    GRID = 'GRID', 'GRID'
    OTHER = 'Other', 'Other'

class ResourceTypeChoices(models.TextChoices):
    METADATA = 'Metadata', 'Metadata'
    RESOURCE = 'Resource', 'Resource'
    SEARCH_SERVICE = 'SearchService', 'Search Service'
    SEARCH_PAGE = 'SearchPage', 'Search Page'
    LANDING_PAGE = 'LandingPage', 'Landing Page'

class BLAMBundle(models.Model):
    bundle_version = models.CharField(max_length=50, null=False)
    bundle_display_title = models.CharField(max_length=255, null=False)
    bundle_description = models.TextField(null=False)
    bundle_recording_date = models.CharField(
        max_length=10,
        null=False,
        validators=[RegexValidator(
            regex=r'([0-9]{4}(-(0[1-9]|1[012])(-([0-2][0-9]|3[01]))?)?)|Unknown',
            message='Date must be in YYYY[-MM[-DD]] format or "Unknown"'
        )]
    )
    bundle_publication_year = models.IntegerField(null=False)
    bundle_data_provider = models.CharField(max_length=255, null=False)
    access = models.CharField(
        max_length=50,
        choices=AccessChoices.choices,
        default=AccessChoices.OPEN,
        null=False
    )
    availability_date = models.DateField(null=False)
    bundle_is_member_of_collection = models.CharField(max_length=255, null=False)
    bundle_is_member_of_collection_type = models.CharField(
        max_length=10,
        choices=BundleCollectionIdentifierTypeChoices.choices,
        default=BundleCollectionIdentifierTypeChoices.HANDLE,
        null=False
    )
    md_license = models.CharField(max_length=255, null=False)
    md_license_uri = models.URLField(null=False)

    def __str__(self):
        return self.bundle_display_title

class BundleIdentifier(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE, related_name='bundle_ids')
    value = models.URLField(max_length=255, null=False)
    identifier_type = models.CharField(
        max_length=10,
        choices=IdentifierTypeChoices.choices,
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.identifier_type}: {self.value}"

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(bundle__bundle_ids__count__gte=1),
                name='bundle_has_at_least_one_id'
            )
        ]

class BundleKeyword(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE, related_name='keywords')
    keyword = models.CharField(max_length=100, null=False)

    def __str__(self):
        return self.keyword

class ObjectLanguage(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE, related_name='languages')
    display_name = models.CharField(max_length=255, null=False)
    name = models.CharField(max_length=255, null=False)
    iso_639_3_code = models.CharField(
        max_length=3,
        null=False,
        validators=[RegexValidator(
            regex=r'[a-z]{3}',
            message='ISO code must be exactly 3 lowercase letters'
        )]
    )
    glottolog_code = models.CharField(
        max_length=8,
        null=False,
        validators=[RegexValidator(
            regex=r'[a-z]{4}[0-9]{4}',
            message='Glottolog code must be 4 lowercase letters followed by 4 digits'
        )]
    )
    language_family = models.CharField(max_length=255, null=False)

    def __str__(self):
        return self.display_name

class ObjectLanguageAlternativeName(models.Model):
    language = models.ForeignKey(ObjectLanguage, on_delete=models.CASCADE, related_name='alternative_names')
    name = models.CharField(max_length=255, null=False)

    def __str__(self):
        return self.name

class BundleLocation(models.Model):
    bundle = models.OneToOneField(BLAMBundle, on_delete=models.CASCADE, related_name='location')
    geo_location = models.CharField(max_length=255, blank=True, null=True)
    location_name = models.CharField(max_length=255, blank=True, null=True)
    location_facet = models.CharField(max_length=255, blank=True, null=True)
    region_name = models.CharField(max_length=255, null=False)
    region_facet = models.CharField(max_length=255, null=False)
    country_name = models.CharField(max_length=255, null=False)
    country_facet = models.CharField(max_length=255, null=False)
    country_code = models.CharField(
        max_length=2,
        null=False,
        validators=[RegexValidator(
            regex=r'[A-Z]{2}',
            message='Country code must be exactly 2 uppercase letters'
        )]
    )

    def __str__(self):
        return self.location_name or 'Unknown Location'

class Creator(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE, related_name='creators')
    name_identifier = models.CharField(max_length=255, blank=True, null=True)
    name_identifier_type = models.CharField(
        max_length=10,
        choices=NameIdentifierTypeChoices.choices,
        blank=True,
        null=True
    )
    affiliation = models.CharField(max_length=255, blank=True, null=True)
    family_name = models.CharField(max_length=255, null=False)
    given_name = models.CharField(max_length=255, blank=True, null=True)
    order = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.given_name} {self.family_name}"

class Contributor(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE, related_name='contributors')
    name_identifier = models.CharField(max_length=255, blank=True, null=True)
    name_identifier_type = models.CharField(
        max_length=10,
        choices=NameIdentifierTypeChoices.choices,
        blank=True,
        null=True
    )
    affiliation = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=100, null=False)
    family_name = models.CharField(max_length=255, null=False)
    given_name = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.given_name} {self.family_name} ({self.role})"

class Project(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE, related_name='projects')
    display_name = models.CharField(max_length=255, null=False)
    description = models.TextField(null=False)

    def __str__(self):
        return self.display_name

class Funder(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='funders')
    name = models.CharField(max_length=255, null=False)
    identifier = models.CharField(max_length=255, blank=True, null=True)
    identifier_type = models.CharField(
        max_length=20,
        choices=FunderIdentifierTypeChoices.choices,
        blank=True,
        null=True
    )
    grant_identifier = models.CharField(max_length=255, blank=True, null=True)
    grant_uri = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name

class License(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE, related_name='licenses')
    name = models.CharField(max_length=255, null=False)
    identifier = models.CharField(max_length=255, null=False)

    def __str__(self):
        return self.name

class RightsHolder(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE, related_name='rights_holders')
    name = models.CharField(max_length=255, null=False)
    identifier = models.CharField(max_length=255, blank=True, null=True)
    identifier_type = models.CharField(
        max_length=10,
        choices=NameIdentifierTypeChoices.choices,
        blank=True,
        null=True
    )

    def __str__(self):
        return self.name

class Resource(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE, related_name='%(class)ss')
    ref = models.CharField(max_length=255, null=False)
    file_name = models.CharField(max_length=255, null=False)
    file_pid = models.CharField(max_length=255, null=False)
    mime_type = models.CharField(max_length=100, null=False)
    file_description = models.TextField(blank=True, null=True)
    resource_type = models.CharField(
        max_length=20,
        choices=ResourceTypeChoices.choices,
        default=ResourceTypeChoices.RESOURCE,
        null=False
    )

    class Meta:
        abstract = True

class MediaResource(Resource):
    file_length = models.CharField(max_length=100, null=False)

    class Meta:
        verbose_name = 'Media Resource'
        verbose_name_plural = 'Media Resources'

class WrittenResource(Resource):
    is_annotation_of = models.ManyToManyField(MediaResource, blank=True)

    class Meta:
        verbose_name = 'Written Resource'
        verbose_name_plural = 'Written Resources'

class OtherResource(Resource):
    class Meta:
        verbose_name = 'Other Resource'
        verbose_name_plural = 'Other Resources'

class BundleAdditionalMetadataFile(Resource):
    is_metadata_for = models.ForeignKey('Resource', on_delete=models.CASCADE)

class SegmentationUnit(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE)
    unit = models.CharField(max_length=255)

class TranscriptionType(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE)
    type = models.CharField(max_length=255)

class TranslationLanguage(models.Model):
    bundle = models.ForeignKey(BLAMBundle, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=3)  # ISO 639-3