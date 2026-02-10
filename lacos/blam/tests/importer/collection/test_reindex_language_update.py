"""Tests for language field updates during collection reindex."""

import pytest

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.models.collection.collection_general_info import (
    CollectionObjectLanguage,
)


def _build_collection_xml(
    self_link="hdl:test/reindex-lang-001",
    languages=None,
):
    """Build a minimal valid BLAM v1.2 collection XML."""
    if languages is None:
        languages = [
            {
                "display_name": "English",
                "name": "English",
                "iso": "eng",
                "glottolog": "stan1293",
            }
        ]

    lang_xml = ""
    for lang in languages:
        lang_xml += f"""
            <CollectionObjectLanguage>
              <ObjectLanguageDisplayName>{lang['display_name']}</ObjectLanguageDisplayName>
              <ObjectLanguageName>{lang['name']}</ObjectLanguageName>
              <ObjectLanguageISO639-3Code>{lang['iso']}</ObjectLanguageISO639-3Code>
              <ObjectLanguageGlottologCode>{lang['glottolog']}</ObjectLanguageGlottologCode>
            </CollectionObjectLanguage>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CMD xmlns="http://www.clarin.eu/cmd/">
  <Header>
    <MdCreator>test</MdCreator>
    <MdCreationDate>2024-01-01</MdCreationDate>
    <MdSelfLink>{self_link}</MdSelfLink>
    <MdProfile>clarin.eu:cr1:p_test</MdProfile>
    <MdCollectionDisplayName>Test</MdCollectionDisplayName>
  </Header>
  <Resources>
    <ResourceProxyList/>
    <JournalFileProxyList/>
    <ResourceRelationList/>
  </Resources>
  <Components>
    <BLAM-collection-repository_v1.2>
      <MDLicense URI="https://creativecommons.org/licenses/by/4.0/">CC-BY-4.0</MDLicense>
      <CollectionGeneralInfo>
        <CollectionID IdentifierType="Handle">{self_link}</CollectionID>
        <CollectionVersion>1.0</CollectionVersion>
        <CollectionDisplayTitle>Test Collection</CollectionDisplayTitle>
        <CollectionDescription>A test collection.</CollectionDescription>
        <CollectionObjectLanguages>{lang_xml}
        </CollectionObjectLanguages>
        <CollectionLocation>
          <CollectionCountryName>Germany</CollectionCountryName>
          <CollectionCountryFacet>Germany</CollectionCountryFacet>
          <CollectionCountryCode>DE</CollectionCountryCode>
        </CollectionLocation>
      </CollectionGeneralInfo>
      <CollectionPublicationInfo>
        <CollectionPublicationYear>2024</CollectionPublicationYear>
        <CollectionDataProvider>Test Provider</CollectionDataProvider>
        <CollectionCreators>
          <CollectionCreator>
            <CreatorName>
              <CreatorFamilyName>Smith</CreatorFamilyName>
              <CreatorGivenName>John</CreatorGivenName>
            </CreatorName>
          </CollectionCreator>
        </CollectionCreators>
      </CollectionPublicationInfo>
      <CollectionAdministrativeInfo>
        <Access>open</Access>
        <AvailabilityDate>2024-01-01</AvailabilityDate>
        <License>
          <LicenseName>CC-BY-4.0</LicenseName>
          <LicenseIdentifier>https://creativecommons.org/licenses/by/4.0/</LicenseIdentifier>
        </License>
        <RightsHolder>
          <RightsHolderName>Test University</RightsHolderName>
        </RightsHolder>
      </CollectionAdministrativeInfo>
      <CollectionStructuralInfo>
        <CollectionMembers>
          <CollectionHasCollectionMember IdentifierType="Handle">hdl:test/bundle-001</CollectionHasCollectionMember>
        </CollectionMembers>
      </CollectionStructuralInfo>
    </BLAM-collection-repository_v1.2>
  </Components>
</CMD>"""


def _get_lang(collection, iso_code):
    """Get a language from a collection's general_info by ISO code."""
    return collection.general_info.first().object_languages.get(iso_639_3_code=iso_code)


@pytest.mark.django_db
def test_reindex_updates_language_display_name():
    """Language display_name should change after reindex with updated XML."""
    xml_v1 = _build_collection_xml(
        languages=[
            {
                "display_name": "Portuguese",
                "name": "Portuguese",
                "iso": "por",
                "glottolog": "port1283",
            }
        ]
    )
    collection = CollectionImporter.import_from_xml(xml_v1)
    lang = _get_lang(collection, "por")
    assert lang.display_name == "Portuguese"

    # Reindex with updated display_name
    xml_v2 = _build_collection_xml(
        languages=[
            {
                "display_name": "Brazilian Portuguese",
                "name": "Portuguese",
                "iso": "por",
                "glottolog": "port1283",
            }
        ]
    )
    CollectionImporter.import_from_xml(xml_v2, update_existing=True)
    lang = _get_lang(collection, "por")
    assert lang.display_name == "Brazilian Portuguese"


@pytest.mark.django_db
def test_reindex_updates_language_name():
    """Language name should change after reindex with updated XML."""
    xml_v1 = _build_collection_xml(
        languages=[
            {
                "display_name": "Spanish",
                "name": "Spanish",
                "iso": "spa",
                "glottolog": "stan1288",
            }
        ]
    )
    collection = CollectionImporter.import_from_xml(xml_v1)
    lang = _get_lang(collection, "spa")
    assert lang.name == "Spanish"

    xml_v2 = _build_collection_xml(
        languages=[
            {
                "display_name": "Spanish",
                "name": "Cuban Spanish",
                "iso": "spa",
                "glottolog": "stan1288",
            }
        ]
    )
    CollectionImporter.import_from_xml(xml_v2, update_existing=True)
    lang = _get_lang(collection, "spa")
    assert lang.name == "Cuban Spanish"


@pytest.mark.django_db
def test_reindex_updates_language_glottolog_code():
    """Language glottolog_code should change after reindex with updated XML."""
    xml_v1 = _build_collection_xml(
        languages=[
            {
                "display_name": "English",
                "name": "English",
                "iso": "eng",
                "glottolog": "stan1293",
            }
        ]
    )
    collection = CollectionImporter.import_from_xml(xml_v1)
    lang = _get_lang(collection, "eng")
    assert lang.glottolog_code == "stan1293"

    xml_v2 = _build_collection_xml(
        languages=[
            {
                "display_name": "English",
                "name": "English",
                "iso": "eng",
                "glottolog": "engl1234",
            }
        ]
    )
    CollectionImporter.import_from_xml(xml_v2, update_existing=True)
    lang = _get_lang(collection, "eng")
    assert lang.glottolog_code == "engl1234"


@pytest.mark.django_db
def test_reindex_adds_new_language():
    """Reindex should add languages that weren't in the original import."""
    xml_v1 = _build_collection_xml(
        languages=[
            {
                "display_name": "English",
                "name": "English",
                "iso": "eng",
                "glottolog": "stan1293",
            }
        ]
    )
    collection = CollectionImporter.import_from_xml(xml_v1)
    general_info = collection.general_info.first()
    assert general_info.object_languages.count() == 1

    xml_v2 = _build_collection_xml(
        languages=[
            {
                "display_name": "English",
                "name": "English",
                "iso": "eng",
                "glottolog": "stan1293",
            },
            {
                "display_name": "Portuguese",
                "name": "Portuguese",
                "iso": "por",
                "glottolog": "port1283",
            },
        ]
    )
    CollectionImporter.import_from_xml(xml_v2, update_existing=True)
    general_info.refresh_from_db()
    assert general_info.object_languages.count() == 2
    assert general_info.object_languages.filter(iso_639_3_code="por").exists()


@pytest.mark.django_db
def test_reindex_removes_language_from_collection():
    """Reindex should remove languages no longer in the XML."""
    xml_v1 = _build_collection_xml(
        languages=[
            {
                "display_name": "English",
                "name": "English",
                "iso": "eng",
                "glottolog": "stan1293",
            },
            {
                "display_name": "Portuguese",
                "name": "Portuguese",
                "iso": "por",
                "glottolog": "port1283",
            },
        ]
    )
    collection = CollectionImporter.import_from_xml(xml_v1)
    general_info = collection.general_info.first()
    assert general_info.object_languages.count() == 2

    # Reindex with only English — Portuguese should be deleted
    xml_v2 = _build_collection_xml(
        languages=[
            {
                "display_name": "English",
                "name": "English",
                "iso": "eng",
                "glottolog": "stan1293",
            }
        ]
    )
    CollectionImporter.import_from_xml(xml_v2, update_existing=True)
    general_info.refresh_from_db()
    assert general_info.object_languages.count() == 1
    assert general_info.object_languages.first().iso_639_3_code == "eng"


@pytest.mark.django_db
def test_reindex_updates_multiple_languages_simultaneously():
    """All language fields should update when reindexing multiple languages."""
    xml_v1 = _build_collection_xml(
        languages=[
            {
                "display_name": "Portuguese",
                "name": "Portuguese",
                "iso": "por",
                "glottolog": "port1283",
            },
            {
                "display_name": "Spanish",
                "name": "Spanish",
                "iso": "spa",
                "glottolog": "stan1288",
            },
        ]
    )
    collection = CollectionImporter.import_from_xml(xml_v1)

    xml_v2 = _build_collection_xml(
        languages=[
            {
                "display_name": "Brazilian Portuguese",
                "name": "Brazilian Portuguese",
                "iso": "por",
                "glottolog": "port1283",
            },
            {
                "display_name": "Cuban Spanish",
                "name": "Cuban Spanish",
                "iso": "spa",
                "glottolog": "stan1288",
            },
        ]
    )
    CollectionImporter.import_from_xml(xml_v2, update_existing=True)

    por = _get_lang(collection, "por")
    spa = _get_lang(collection, "spa")
    assert por.display_name == "Brazilian Portuguese"
    assert por.name == "Brazilian Portuguese"
    assert spa.display_name == "Cuban Spanish"
    assert spa.name == "Cuban Spanish"


@pytest.mark.django_db
def test_cross_collection_language_isolation():
    """
    FIX: Each collection owns its own language objects.
    Collection B's import must NOT overwrite collection A's language fields.
    """
    # Collection A: "por" = "Brazilian Portuguese"
    xml_a = _build_collection_xml(
        self_link="hdl:test/collection-A",
        languages=[
            {
                "display_name": "Brazilian Portuguese",
                "name": "Brazilian Portuguese",
                "iso": "por",
                "glottolog": "port1283",
            }
        ],
    )
    collection_a = CollectionImporter.import_from_xml(xml_a)
    lang_a = _get_lang(collection_a, "por")
    assert lang_a.display_name == "Brazilian Portuguese"

    # Collection B: same ISO "por" but different display name
    xml_b = _build_collection_xml(
        self_link="hdl:test/collection-B",
        languages=[
            {
                "display_name": "Portuguese",
                "name": "Portuguese",
                "iso": "por",
                "glottolog": "port1283",
            }
        ],
    )
    collection_b = CollectionImporter.import_from_xml(xml_b)

    # Collection A's language must be unchanged
    lang_a = _get_lang(collection_a, "por")
    assert lang_a.display_name == "Brazilian Portuguese"

    # Collection B has its own language object
    lang_b = _get_lang(collection_b, "por")
    assert lang_b.display_name == "Portuguese"

    # They are distinct DB rows
    assert lang_a.pk != lang_b.pk
