from django.db import models


class BLAMCollection(models.Model):
    display_title = models.CharField(max_length=255)
    version = models.CharField(max_length=50)
    description = models.TextField()

    def __str__(self):
        return self.display_title


class CollectionObjectLanguage(models.Model):
    collection = models.ForeignKey(BLAMCollection, on_delete=models.CASCADE, related_name='languages')
    name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    iso_code = models.CharField(max_length=10, blank=True, null=True)
    glottolog_code = models.CharField(max_length=20, blank=True, null=True)
    language_family = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name


class LanguageAlternativeName(models.Model):
    language = models.ForeignKey(CollectionObjectLanguage, on_delete=models.CASCADE, related_name='alternative_names')
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class CollectionLocation(models.Model):
    collection = models.ForeignKey(BLAMCollection, on_delete=models.CASCADE, related_name='locations')
    geo_coordinates = models.CharField(max_length=100, blank=True, null=True)
    location_name = models.CharField(max_length=255)
    location_facet = models.CharField(max_length=255, blank=True, null=True)
    region_name = models.CharField(max_length=255, blank=True, null=True)
    region_facet = models.CharField(max_length=255, blank=True, null=True)
    country_name = models.CharField(max_length=255)
    country_facet = models.CharField(max_length=255, blank=True, null=True)
    country_code = models.CharField(max_length=3)

    def __str__(self):
        return f"{self.location_name}, {self.country_name}"


class CollectionPublicationInfo(models.Model):
    collection = models.OneToOneField(BLAMCollection, on_delete=models.CASCADE, related_name='publication_info')
    publication_year = models.IntegerField()
    data_provider = models.CharField(max_length=255)

    def __str__(self):
        return f"Publication Info for {self.collection.display_title}"


class Creator(models.Model):
    publication_info = models.ForeignKey(CollectionPublicationInfo, on_delete=models.CASCADE, related_name='creators')
    name_identifier = models.CharField(max_length=255, blank=True, null=True)
    affiliation = models.CharField(max_length=255, blank=True, null=True)
    family_name = models.CharField(max_length=255)
    given_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.given_name} {self.family_name}"


class Contributor(models.Model):
    publication_info = models.ForeignKey(CollectionPublicationInfo, on_delete=models.CASCADE, related_name='contributors')
    name_identifier = models.CharField(max_length=255, blank=True, null=True)
    affiliation = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=100)
    family_name = models.CharField(max_length=255)
    given_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.given_name} {self.family_name}"


class CollectionAdministrativeInfo(models.Model):
    collection = models.OneToOneField(BLAMCollection, on_delete=models.CASCADE, related_name='administrative_info')
    access_type = models.CharField(max_length=100)
    availability_date = models.DateField()

    def __str__(self):
        return f"Administrative Info for {self.collection.display_title}"


class License(models.Model):
    administrative_info = models.ForeignKey(CollectionAdministrativeInfo, on_delete=models.CASCADE, related_name='licenses')
    name = models.CharField(max_length=255)
    identifier = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class RightsHolder(models.Model):
    administrative_info = models.ForeignKey(CollectionAdministrativeInfo, on_delete=models.CASCADE, related_name='rights_holders')
    name = models.CharField(max_length=255)
    identifier = models.CharField(max_length=255, blank=True, null=True)
    identifier_type = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name


class CollectionMember(models.Model):
    collection = models.ForeignKey(BLAMCollection, on_delete=models.CASCADE, related_name='members')
    identifier = models.CharField(max_length=255)
    identifier_type = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.identifier_type}: {self.identifier}"
