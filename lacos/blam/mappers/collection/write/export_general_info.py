"""Export collection general info to BLAM schema."""

from django.db.models import QuerySet

from blam_schemas.collection.blam_collection_repository_v1_0 import (
    Cmd,
    CollectionIdIdentifierType,
    ComplextypeObjectLanguageIso6393Code0511 as IsoCodeType,
    ComplextypeObjectLanguageGlottologCode0511 as GlottologCodeType,
    ComplextypeCollectionCountryCode611 as CountryCodeType,
)
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
    CollectionKeyword,
    CollectionObjectLanguage,
)

# Type aliases
GeneralInfoType = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo
CollectionIdType = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionId
KeywordsType = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionKeywords
ObjectLanguagesType = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionObjectLanguages
ObjectLanguageType = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage
AltNamesType = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage.ObjectLanguageAlternativeNames
TaxonomyType = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage.ObjectLanguageTaxonomy
LocationType = Cmd.Components.BlamCollectionRepositoryV10.CollectionGeneralInfo.CollectionLocation


def export_general_info(general_info: CollectionGeneralInfo, repo) -> None:
    """Export collection general info to BLAM schema."""
    info = GeneralInfoType()

    info.collection_id = [_create_collection_id(general_info)]
    info.collection_version = general_info.version
    info.collection_display_title = general_info.display_title
    info.collection_description = general_info.description

    if general_info.keywords.exists():
        info.collection_keywords = _export_keywords(general_info.keywords.all())

    info.collection_object_languages = _export_object_languages(
        general_info.object_languages.all()
    )
    info.collection_location = _export_location(general_info.location)

    repo.collection_general_info = info


def _create_collection_id(general_info: CollectionGeneralInfo) -> CollectionIdType:
    collection_id = CollectionIdType()
    collection_id.value = general_info.id_value
    collection_id.identifier_type = _map_identifier_type(general_info.id_type)
    return collection_id


def _map_identifier_type(id_type: str) -> CollectionIdIdentifierType:
    mapping = {
        IdentifierTypeChoices.DOI: CollectionIdIdentifierType.DOI,
        IdentifierTypeChoices.HANDLE: CollectionIdIdentifierType.HANDLE,
        IdentifierTypeChoices.URN: CollectionIdIdentifierType.URN,
        IdentifierTypeChoices.OTHER: CollectionIdIdentifierType.OTHER,
    }
    return mapping.get(id_type, CollectionIdIdentifierType.DOI)


def _export_keywords(keywords: QuerySet[CollectionKeyword]) -> KeywordsType:
    keywords_data = KeywordsType()
    keywords_data.collection_keyword = [kw.value for kw in keywords]
    return keywords_data


def _export_object_languages(languages: QuerySet[CollectionObjectLanguage]) -> ObjectLanguagesType:
    languages_data = ObjectLanguagesType()
    languages_data.collection_object_language = [
        _export_object_language(lang) for lang in languages
    ]
    return languages_data


def _export_object_language(language: CollectionObjectLanguage) -> ObjectLanguageType:
    lang_data = ObjectLanguageType()

    lang_data.object_language_display_name = [language.display_name]
    lang_data.object_language_name = language.name

    iso_code = IsoCodeType()
    iso_code.value = language.iso_639_3_code
    lang_data.object_language_iso639_3_code = iso_code

    glotto_code = GlottologCodeType()
    glotto_code.value = language.glottolog_code
    lang_data.object_language_glottolog_code = glotto_code

    if language.alternative_names.exists():
        lang_data.object_language_alternative_names = _export_alternative_names(language)

    try:
        taxonomy = language.taxonomy
        lang_data.object_language_taxonomy = _export_taxonomy(taxonomy)
    except Exception:
        pass

    return lang_data


def _export_alternative_names(language: CollectionObjectLanguage) -> AltNamesType:
    alt_names = AltNamesType()
    alt_names.object_language_alternative_name = [
        name.value for name in language.alternative_names.all()
    ]
    return alt_names


def _export_taxonomy(taxonomy) -> TaxonomyType:
    taxonomy_data = TaxonomyType()
    taxonomy_data.object_language_language_family = [
        family.value for family in taxonomy.language_family.all()
    ]
    return taxonomy_data


def _export_location(location: CollectionLocation) -> LocationType:
    loc_data = LocationType()

    if location.geo_location:
        loc_data.collection_geo_location = location.geo_location
    if location.location_name:
        loc_data.collection_location_name = location.location_name
    if location.location_facet:
        loc_data.collection_location_facet = location.location_facet
    if location.region_name:
        loc_data.collection_region_name = location.region_name
    if location.region_facet:
        loc_data.collection_region_facet = location.region_facet
    if location.country_name:
        loc_data.collection_country_name = location.country_name
    if location.country_facet:
        loc_data.collection_country_facet = location.country_facet
    if location.country_code:
        country_code = CountryCodeType()
        country_code.value = location.country_code
        loc_data.collection_country_code = country_code

    return loc_data
