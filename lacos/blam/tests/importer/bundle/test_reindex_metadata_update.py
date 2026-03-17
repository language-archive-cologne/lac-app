import pytest

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.models.bundle.bundle_administrative_info import (
    BundleIdenticalResource,
    BundleLicense,
    BundleRightsHolder,
    BundleRightsHolderIdentifier,
)
from lacos.blam.models.bundle.bundle_general_info import (
    BundleKeyword,
    BundleLocation,
)
from lacos.blam.models.bundle.bundle_publication_info import (
    BundleContributor,
    BundleContributorName,
    BundleCreator,
)


def _build_supporting_collection_xml(self_link: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CMD xmlns="http://www.clarin.eu/cmd/">
  <Header>
    <MdCreator>test</MdCreator>
    <MdCreationDate>2024-01-01</MdCreationDate>
    <MdSelfLink>{self_link}</MdSelfLink>
    <MdProfile>clarin.eu:cr1:p_test</MdProfile>
    <MdCollectionDisplayName>Supporting Collection</MdCollectionDisplayName>
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
        <CollectionDisplayTitle>Supporting Collection</CollectionDisplayTitle>
        <CollectionDescription>Collection required by bundle structural info.</CollectionDescription>
        <CollectionObjectLanguages>
          <CollectionObjectLanguage>
            <ObjectLanguageDisplayName>English</ObjectLanguageDisplayName>
            <ObjectLanguageName>English</ObjectLanguageName>
            <ObjectLanguageISO639-3Code>eng</ObjectLanguageISO639-3Code>
            <ObjectLanguageGlottologCode>stan1293</ObjectLanguageGlottologCode>
          </CollectionObjectLanguage>
        </CollectionObjectLanguages>
        <CollectionLocation>
          <CollectionCountryName>Germany</CollectionCountryName>
          <CollectionCountryFacet>Germany</CollectionCountryFacet>
          <CollectionCountryCode>DE</CollectionCountryCode>
          <CollectionRegionName>North Rhine-Westphalia</CollectionRegionName>
          <CollectionRegionFacet>North Rhine-Westphalia</CollectionRegionFacet>
        </CollectionLocation>
      </CollectionGeneralInfo>
      <CollectionPublicationInfo>
        <CollectionPublicationYear>2024</CollectionPublicationYear>
        <CollectionDataProvider>Test Provider</CollectionDataProvider>
        <CollectionCreators>
          <CollectionCreator>
            <CreatorNameIdentifier IdentifierType="ORCID">https://orcid.org/0000-0000-0000-0001</CreatorNameIdentifier>
            <CreatorName>
              <CreatorFamilyName>Support</CreatorFamilyName>
              <CreatorGivenName>Owner</CreatorGivenName>
            </CreatorName>
          </CollectionCreator>
        </CollectionCreators>
      </CollectionPublicationInfo>
      <CollectionAdministrativeInfo>
        <Access>public</Access>
        <AvailabilityDate>2024-01-01</AvailabilityDate>
        <License>
          <LicenseName>CC-BY-4.0</LicenseName>
          <LicenseIdentifier>https://creativecommons.org/licenses/by/4.0/</LicenseIdentifier>
        </License>
        <RightsHolder>
          <RightsHolderName>Supporting Rights Holder</RightsHolderName>
        </RightsHolder>
      </CollectionAdministrativeInfo>
      <CollectionStructuralInfo>
        <CollectionMembers>
          <CollectionHasCollectionMember IdentifierType="Handle">hdl:test/bundle-placeholder</CollectionHasCollectionMember>
        </CollectionMembers>
      </CollectionStructuralInfo>
    </BLAM-collection-repository_v1.2>
  </Components>
</CMD>"""


def _build_bundle_xml(
    *,
    self_link: str,
    collection_link: str,
    creator_affiliation: str,
    contributor_affiliation: str | None,
    contributor_role: str | None,
    keyword: str | None,
    location_name: str,
    identical_uri: str | None,
    license_name: str,
    license_identifier: str,
    rights_holder_name: str,
    rights_holder_identifier: str,
    extra_keywords: list[str] | None = None,
    extra_rights_holders: list[tuple[str, str]] | None = None,
) -> str:
    keywords_xml = ""
    keyword_values = [value for value in [keyword, *(extra_keywords or [])] if value]
    if keyword_values:
        keyword_items = "".join(
            f"\n          <BundleKeyword>{value}</BundleKeyword>" for value in keyword_values
        )
        keywords_xml = f"""
        <BundleKeywords>{keyword_items}
        </BundleKeywords>"""

    contributors_xml = ""
    if contributor_affiliation is not None and contributor_role is not None:
        contributors_xml = f"""
        <BundleContributors>
          <BundleContributor>
            <ContributorNameIdentifier IdentifierType="ISNI">https://isni.org/isni/000000012146438X</ContributorNameIdentifier>
            <ContributorAffiliation>{contributor_affiliation}</ContributorAffiliation>
            <ContributorRole>{contributor_role}</ContributorRole>
            <ContributorName>
              <ContributorFamilyName>Taylor</ContributorFamilyName>
              <ContributorGivenName>Mia</ContributorGivenName>
            </ContributorName>
          </BundleContributor>
        </BundleContributors>"""

    identical_xml = ""
    if identical_uri is not None:
        identical_xml = f"""
        <BundleIsIdenticalTo>{identical_uri}</BundleIsIdenticalTo>"""

    rights_holders = [(rights_holder_name, rights_holder_identifier), *(extra_rights_holders or [])]
    rights_holders_xml = "".join(
        f"""
        <RightsHolder>
          <RightsHolderName>{name}</RightsHolderName>
          <RightsHolderIdentifier IdentifierType="ISNI">{identifier}</RightsHolderIdentifier>
        </RightsHolder>"""
        for name, identifier in rights_holders
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CMD xmlns="http://www.clarin.eu/cmd/" CMDVersion="1.1">
  <Header>
    <MdCreator>test</MdCreator>
    <MdCreationDate>2024-01-01</MdCreationDate>
    <MdSelfLink>{self_link}</MdSelfLink>
    <MdProfile>clarin.eu:cr1:p_test</MdProfile>
  </Header>
  <Resources>
    <ResourceProxyList/>
    <JournalFileProxyList/>
    <ResourceRelationList/>
  </Resources>
  <Components>
    <BLAM-bundle-repository_v1.1>
      <MDLicense URI="https://creativecommons.org/licenses/by/4.0/">CC-BY-4.0</MDLicense>
      <BundleGeneralInfo>
        <BundleID IdentifierType="Handle">{self_link}</BundleID>
        <BundleVersion>1.0</BundleVersion>
        <BundleDisplayTitle>Test Bundle</BundleDisplayTitle>
        <BundleDescription>A test bundle.</BundleDescription>
        <BundleRecordingDate>2024-01-01</BundleRecordingDate>
{keywords_xml}
        <BundleObjectLanguages>
          <BundleObjectLanguage>
            <ObjectLanguageDisplayName>English</ObjectLanguageDisplayName>
            <ObjectLanguageName>English</ObjectLanguageName>
            <ObjectLanguageISO639-3Code>eng</ObjectLanguageISO639-3Code>
            <ObjectLanguageGlottologCode>stan1293</ObjectLanguageGlottologCode>
          </BundleObjectLanguage>
        </BundleObjectLanguages>
        <BundleLocation>
          <BundleLocationName>{location_name}</BundleLocationName>
          <BundleRegionName>North Rhine-Westphalia</BundleRegionName>
          <BundleRegionFacet>North Rhine-Westphalia</BundleRegionFacet>
          <BundleCountryName>Germany</BundleCountryName>
          <BundleCountryFacet>Germany</BundleCountryFacet>
          <BundleCountryCode>DE</BundleCountryCode>
        </BundleLocation>
      </BundleGeneralInfo>
      <BundlePublicationInfo>
        <BundlePublicationYear>2024</BundlePublicationYear>
        <BundleDataProvider>Test Provider</BundleDataProvider>
        <BundleCreators>
          <BundleCreator>
            <CreatorNameIdentifier IdentifierType="ORCID">https://orcid.org/0000-0000-0000-0001</CreatorNameIdentifier>
            <CreatorAffiliation>{creator_affiliation}</CreatorAffiliation>
            <CreatorName>
              <CreatorFamilyName>Smith</CreatorFamilyName>
              <CreatorGivenName>John</CreatorGivenName>
            </CreatorName>
          </BundleCreator>
        </BundleCreators>
{contributors_xml}
      </BundlePublicationInfo>
      <BundleAdministrativeInfo>
{identical_xml}
        <Access>public</Access>
        <AvailabilityDate>2024-01-01</AvailabilityDate>
        <License>
          <LicenseName>{license_name}</LicenseName>
          <LicenseIdentifier>{license_identifier}</LicenseIdentifier>
        </License>
{rights_holders_xml}
      </BundleAdministrativeInfo>
      <BundleStructuralInfo>
        <BundleIsMemberOfCollection IdentifierType="Handle">{collection_link}</BundleIsMemberOfCollection>
        <BundleResources/>
      </BundleStructuralInfo>
    </BLAM-bundle-repository_v1.1>
  </Components>
</CMD>"""


@pytest.mark.django_db
def test_bundle_reindex_replaces_owned_metadata():
    collection_link = "hdl:test/bundle-supporting-collection"
    CollectionImporter.import_from_xml(_build_supporting_collection_xml(collection_link))

    xml_v1 = _build_bundle_xml(
        self_link="hdl:test/bundle-metadata-001",
        collection_link=collection_link,
        creator_affiliation="University A",
        contributor_affiliation="Institute A",
        contributor_role="Editor",
        keyword="keyword-one",
        location_name="Village One",
        identical_uri="https://example.com/bundles/identical-one",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Rights Holder A",
        rights_holder_identifier="https://example.com/holders/a",
    )
    bundle, _ = BundleImporter.import_from_xml(xml_v1)

    xml_v2 = _build_bundle_xml(
        self_link="hdl:test/bundle-metadata-001",
        collection_link=collection_link,
        creator_affiliation="University B",
        contributor_affiliation="Institute B",
        contributor_role="Translator",
        keyword="keyword-two",
        location_name="Village Two",
        identical_uri="https://example.com/bundles/identical-two",
        license_name="CC-BY-SA-4.0",
        license_identifier="https://creativecommons.org/licenses/by-sa/4.0/",
        rights_holder_name="Rights Holder B",
        rights_holder_identifier="https://example.com/holders/b",
    )
    BundleImporter.import_from_xml(xml_v2, update_existing=True)

    publication_info = bundle.publication_info.get()
    general_info = bundle.general_info.get()
    admin_info = bundle.administrative_info.get()

    creator = publication_info.creators.get()
    contributor = publication_info.contributors.get()
    assert creator.affiliation == "University B"
    assert contributor.affiliation == "Institute B"
    assert contributor.role == "Translator"
    assert BundleCreator.objects.count() == 1
    assert BundleContributor.objects.count() == 1
    assert BundleContributorName.objects.count() == 1

    assert list(general_info.keywords.values_list("value", flat=True)) == ["keyword-two"]
    assert general_info.location.location_name == "Village Two"
    assert BundleKeyword.objects.count() == 1
    assert BundleLocation.objects.count() == 1

    assert list(admin_info.is_identical_to.values_list("uri", flat=True)) == [
        "https://example.com/bundles/identical-two"
    ]
    assert list(admin_info.licenses.values_list("license_name", flat=True)) == ["CC-BY-SA-4.0"]
    assert list(admin_info.rights_holders.values_list("rights_holder_name", flat=True)) == [
        "Rights Holder B"
    ]
    assert BundleIdenticalResource.objects.count() == 1
    assert BundleLicense.objects.count() == 1
    assert BundleRightsHolder.objects.count() == 1
    assert BundleRightsHolderIdentifier.objects.count() == 1


@pytest.mark.django_db
def test_bundle_reindex_isolates_owned_metadata_between_bundles():
    collection_link = "hdl:test/bundle-supporting-collection-isolation"
    CollectionImporter.import_from_xml(_build_supporting_collection_xml(collection_link))

    xml_a = _build_bundle_xml(
        self_link="hdl:test/bundle-metadata-A",
        collection_link=collection_link,
        creator_affiliation="Bundle A University",
        contributor_affiliation="Bundle A Institute",
        contributor_role="Editor",
        keyword="keyword-a",
        location_name="Village A",
        identical_uri="https://example.com/bundles/identical-a",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Shared Rights Holder",
        rights_holder_identifier="https://example.com/holders/a",
    )
    bundle_a, _ = BundleImporter.import_from_xml(xml_a)

    xml_b = _build_bundle_xml(
        self_link="hdl:test/bundle-metadata-B",
        collection_link=collection_link,
        creator_affiliation="Bundle B University",
        contributor_affiliation="Bundle B Institute",
        contributor_role="Translator",
        keyword="keyword-b",
        location_name="Village B",
        identical_uri="https://example.com/bundles/identical-b",
        license_name="CC-BY-SA-4.0",
        license_identifier="https://creativecommons.org/licenses/by-sa/4.0/",
        rights_holder_name="Shared Rights Holder",
        rights_holder_identifier="https://example.com/holders/b",
    )
    bundle_b, _ = BundleImporter.import_from_xml(xml_b)

    creator_a = bundle_a.publication_info.get().creators.get()
    creator_b = bundle_b.publication_info.get().creators.get()
    assert creator_a.affiliation == "Bundle A University"
    assert creator_b.affiliation == "Bundle B University"
    assert creator_a.pk != creator_b.pk

    contributor_a = bundle_a.publication_info.get().contributors.get()
    contributor_b = bundle_b.publication_info.get().contributors.get()
    assert contributor_a.affiliation == "Bundle A Institute"
    assert contributor_a.role == "Editor"
    assert contributor_b.affiliation == "Bundle B Institute"
    assert contributor_b.role == "Translator"
    assert contributor_a.pk != contributor_b.pk

    rights_holder_a = bundle_a.administrative_info.get().rights_holders.get()
    rights_holder_b = bundle_b.administrative_info.get().rights_holders.get()
    assert rights_holder_a.rights_holder_identifiers.get().identifier == "https://example.com/holders/a"
    assert rights_holder_b.rights_holder_identifiers.get().identifier == "https://example.com/holders/b"
    assert rights_holder_a.pk != rights_holder_b.pk


@pytest.mark.django_db
def test_bundle_reindex_is_idempotent_for_same_xml():
    collection_link = "hdl:test/bundle-supporting-collection-idempotent"
    CollectionImporter.import_from_xml(_build_supporting_collection_xml(collection_link))

    xml = _build_bundle_xml(
        self_link="hdl:test/bundle-idempotent-001",
        collection_link=collection_link,
        creator_affiliation="University Stable",
        contributor_affiliation="Institute Stable",
        contributor_role="Editor",
        keyword="keyword-stable",
        location_name="Village Stable",
        identical_uri="https://example.com/bundles/identical-stable",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Rights Holder Stable",
        rights_holder_identifier="https://example.com/holders/stable",
    )
    bundle, _ = BundleImporter.import_from_xml(xml)
    BundleImporter.import_from_xml(xml, update_existing=True)

    assert bundle.publication_info.get().creators.count() == 1
    assert bundle.publication_info.get().contributors.count() == 1
    assert bundle.general_info.get().keywords.count() == 1
    assert bundle.administrative_info.get().rights_holders.count() == 1
    assert BundleCreator.objects.count() == 1
    assert BundleContributor.objects.count() == 1
    assert BundleContributorName.objects.count() == 1
    assert BundleKeyword.objects.count() == 1
    assert BundleLicense.objects.count() == 1
    assert BundleRightsHolder.objects.count() == 1
    assert BundleRightsHolderIdentifier.objects.count() == 1


@pytest.mark.django_db
def test_bundle_reindex_handles_list_diffs_and_optional_section_removal():
    collection_link = "hdl:test/bundle-supporting-collection-list-diff"
    CollectionImporter.import_from_xml(_build_supporting_collection_xml(collection_link))

    xml_v1 = _build_bundle_xml(
        self_link="hdl:test/bundle-list-diff-001",
        collection_link=collection_link,
        creator_affiliation="University A",
        contributor_affiliation="Institute A",
        contributor_role="Editor",
        keyword="keyword-one",
        extra_keywords=["keyword-two"],
        location_name="Village One",
        identical_uri="https://example.com/bundles/identical-one",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Rights Holder A",
        rights_holder_identifier="https://example.com/holders/a",
        extra_rights_holders=[("Rights Holder B", "https://example.com/holders/b")],
    )
    bundle, _ = BundleImporter.import_from_xml(xml_v1)

    xml_v2 = _build_bundle_xml(
        self_link="hdl:test/bundle-list-diff-001",
        collection_link=collection_link,
        creator_affiliation="University A",
        contributor_affiliation=None,
        contributor_role=None,
        keyword=None,
        extra_keywords=["keyword-two", "keyword-three"],
        location_name="Village One",
        identical_uri=None,
        license_name="CC-BY-SA-4.0",
        license_identifier="https://creativecommons.org/licenses/by-sa/4.0/",
        rights_holder_name="Rights Holder B",
        rights_holder_identifier="https://example.com/holders/b",
        extra_rights_holders=[("Rights Holder C", "https://example.com/holders/c")],
    )
    BundleImporter.import_from_xml(xml_v2, update_existing=True)

    general_info = bundle.general_info.get()
    publication_info = bundle.publication_info.get()
    admin_info = bundle.administrative_info.get()

    assert sorted(general_info.keywords.values_list("value", flat=True)) == [
        "keyword-three",
        "keyword-two",
    ]
    assert publication_info.contributors.count() == 0
    assert list(admin_info.is_identical_to.values_list("uri", flat=True)) == []
    assert sorted(admin_info.rights_holders.values_list("rights_holder_name", flat=True)) == [
        "Rights Holder B",
        "Rights Holder C",
    ]
    assert BundleKeyword.objects.count() == 2
    assert BundleContributor.objects.count() == 0
    assert BundleContributorName.objects.count() == 0
    assert BundleIdenticalResource.objects.count() == 0
    assert BundleRightsHolder.objects.count() == 2
    assert BundleRightsHolderIdentifier.objects.count() == 2
