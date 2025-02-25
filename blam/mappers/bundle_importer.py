# Remove this import:
# from django.contrib.gis.geos import Point

class BundleImporter:
    @classmethod
    def import_from_xml(cls, xml_content):
        # If there's code that creates a Point object, replace it with string coordinates
        # For example, if you had something like:
        # location.geo_location = Point(longitude, latitude)
        # Replace it with:
        if longitude is not None and latitude is not None:
            location.geo_location = f"{latitude},{longitude}"