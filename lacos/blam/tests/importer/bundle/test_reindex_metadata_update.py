import pytest

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.mappers.bundle.write.bundle_exporter import BundleExporter
from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.models.base_project_info import (
    FunderIdentifier,
    FunderInfo,
    ProjectInfo,
)
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
    BundlePublicationInfoCreator,
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
    project_description: str | None = None,
    funder_name: str | None = None,
    funder_identifier: str | None = None,
    creator_specs: list[dict[str, object]] | None = None,
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

    project_xml = ""
    if project_description is not None and funder_name is not None and funder_identifier is not None:
        project_xml = f"""
      <ProjectInfo>
        <Project>
          <ProjectDisplayName>Bundle Project</ProjectDisplayName>
          <ProjectDescription>{project_description}</ProjectDescription>
          <FunderInfos>
            <FunderInfo>
              <FunderName>{funder_name}</FunderName>
              <FunderIdentifier IdentifierType="ISNI">{funder_identifier}</FunderIdentifier>
              <GrantIdentifier>grant-123</GrantIdentifier>
              <GrantURI>https://example.com/grants/123</GrantURI>
            </FunderInfo>
          </FunderInfos>
        </Project>
      </ProjectInfo>"""

    creator_specs = creator_specs or [
        {
            "order": None,
            "family_name": "Smith",
            "given_name": "John",
            "identifier": "https://orcid.org/0000-0000-0000-0001",
            "affiliation": creator_affiliation,
        }
    ]
    creators_xml = "".join(
        f"""
          <BundleCreator{f' Order="{spec["order"]}"' if spec.get("order") is not None else ""}>
            <CreatorNameIdentifier IdentifierType="ORCID">{spec.get("identifier", "https://orcid.org/0000-0000-0000-0001")}</CreatorNameIdentifier>
            <CreatorAffiliation>{spec.get("affiliation", creator_affiliation)}</CreatorAffiliation>
            <CreatorName>
              <CreatorFamilyName>{spec["family_name"]}</CreatorFamilyName>
              <CreatorGivenName>{spec["given_name"]}</CreatorGivenName>
            </CreatorName>
          </BundleCreator>"""
        for spec in creator_specs
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
        <BundleCreators>{creators_xml}
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
{project_xml}
    </BLAM-bundle-repository_v1.1>
  </Components>
</CMD>"""


@pytest.mark.django_db
def test_bundle_creator_order_uses_xml_element_sequence():
    collection_link = "hdl:test/bundle-supporting-collection-order-attribute"
    CollectionImporter.import_from_xml(_build_supporting_collection_xml(collection_link))
    xml = _build_bundle_xml(
        self_link="hdl:test/bundle-creator-order-attribute",
        collection_link=collection_link,
        creator_affiliation="University Stable",
        contributor_affiliation=None,
        contributor_role=None,
        keyword="keyword-stable",
        location_name="Village Stable",
        identical_uri="https://example.com/bundles/identical-stable",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Rights Holder Stable",
        rights_holder_identifier="https://example.com/holders/stable",
        creator_specs=[
            {
                "order": 2,
                "family_name": "ElementFirst",
                "given_name": "Ada",
                "identifier": "https://orcid.org/0000-0000-0000-0002",
                "affiliation": "University Stable",
            },
            {
                "order": 0,
                "family_name": "OrderZero",
                "given_name": "Ben",
                "identifier": "https://orcid.org/0000-0000-0000-0000",
                "affiliation": "University Stable",
            },
            {
                "order": 1,
                "family_name": "OrderOne",
                "given_name": "Cara",
                "identifier": "https://orcid.org/0000-0000-0000-0001",
                "affiliation": "University Stable",
            },
        ],
    )

    bundle, _ = BundleImporter.import_from_xml(xml)
    publication_info = bundle.publication_info.get()

    ordered_links = (
        BundlePublicationInfoCreator.objects.filter(
            bundlepublicationinfo=publication_info
        )
        .select_related("bundlecreator")
        .order_by("order", "pk")
    )
    assert [
        (link.order, link.bundlecreator.family_name)
        for link in ordered_links
    ] == [
        (0, "ElementFirst"),
        (1, "OrderZero"),
        (2, "OrderOne"),
    ]

    exported_xml = BundleExporter().export(bundle)
    assert exported_xml.index("<CreatorFamilyName>ElementFirst</CreatorFamilyName>") < exported_xml.index(
        "<CreatorFamilyName>OrderZero</CreatorFamilyName>"
    )
    assert exported_xml.index("<CreatorFamilyName>OrderZero</CreatorFamilyName>") < exported_xml.index(
        "<CreatorFamilyName>OrderOne</CreatorFamilyName>"
    )


@pytest.mark.django_db
def test_bundle_creator_order_falls_back_to_element_sequence():
    collection_link = "hdl:test/bundle-supporting-collection-order-fallback"
    CollectionImporter.import_from_xml(_build_supporting_collection_xml(collection_link))
    xml = _build_bundle_xml(
        self_link="hdl:test/bundle-creator-order-fallback",
        collection_link=collection_link,
        creator_affiliation="University Stable",
        contributor_affiliation=None,
        contributor_role=None,
        keyword="keyword-stable",
        location_name="Village Stable",
        identical_uri="https://example.com/bundles/identical-stable",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Rights Holder Stable",
        rights_holder_identifier="https://example.com/holders/stable",
        creator_specs=[
            {
                "family_name": "ElementZero",
                "given_name": "Ada",
                "identifier": "https://orcid.org/0000-0000-0000-0010",
                "affiliation": "University Stable",
            },
            {
                "family_name": "ElementOne",
                "given_name": "Ben",
                "identifier": "https://orcid.org/0000-0000-0000-0011",
                "affiliation": "University Stable",
            },
        ],
    )

    bundle, _ = BundleImporter.import_from_xml(xml)
    publication_info = bundle.publication_info.get()

    ordered_links = (
        BundlePublicationInfoCreator.objects.filter(
            bundlepublicationinfo=publication_info
        )
        .select_related("bundlecreator")
        .order_by("order", "pk")
    )
    assert [
        (link.order, link.bundlecreator.family_name)
        for link in ordered_links
    ] == [
        (0, "ElementZero"),
        (1, "ElementOne"),
    ]


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
        project_description="Original bundle project",
        funder_name="Funder A",
        funder_identifier="https://example.com/funders/a",
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
        project_description="Updated bundle project",
        funder_name="Funder B",
        funder_identifier="https://example.com/funders/b",
    )
    BundleImporter.import_from_xml(xml_v2, update_existing=True)

    publication_info = bundle.publication_info.get()
    general_info = bundle.general_info.get()
    admin_info = bundle.administrative_info.get()
    project = bundle.projects.get()

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
    assert project.project_description == "Updated bundle project"
    funder = project.funder_infos.get()
    assert funder.funder_name == "Funder B"
    assert funder.funder_identifiers.get().value == "https://example.com/funders/b"
    assert ProjectInfo.objects.count() == 1
    assert FunderInfo.objects.count() == 1
    assert FunderIdentifier.objects.count() == 1

    xml_v3 = _build_bundle_xml(
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
    BundleImporter.import_from_xml(xml_v3, update_existing=True)

    bundle.refresh_from_db()
    assert bundle.projects.count() == 0
    assert ProjectInfo.objects.count() == 0
    assert FunderInfo.objects.count() == 0
    assert FunderIdentifier.objects.count() == 0


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
        project_description="Project description A",
        funder_name="Funder A",
        funder_identifier="https://example.com/funders/shared",
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
        project_description="Project description B",
        funder_name="Funder B",
        funder_identifier="https://example.com/funders/shared",
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

    project_a = bundle_a.projects.get()
    project_b = bundle_b.projects.get()
    assert project_a.project_description == "Project description A"
    assert project_b.project_description == "Project description B"
    assert project_a.pk != project_b.pk


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
        project_description="Stable project",
        funder_name="Stable Funder",
        funder_identifier="https://example.com/funders/stable",
    )
    bundle, _ = BundleImporter.import_from_xml(xml)
    BundleImporter.import_from_xml(xml, update_existing=True)

    assert bundle.publication_info.get().creators.count() == 1
    assert bundle.publication_info.get().contributors.count() == 1
    assert bundle.general_info.get().keywords.count() == 1
    assert bundle.administrative_info.get().rights_holders.count() == 1
    assert bundle.projects.count() == 1
    assert BundleCreator.objects.count() == 1
    assert BundleContributor.objects.count() == 1
    assert BundleContributorName.objects.count() == 1
    assert BundleKeyword.objects.count() == 1
    assert BundleLicense.objects.count() == 1
    assert BundleRightsHolder.objects.count() == 1
    assert BundleRightsHolderIdentifier.objects.count() == 1
    assert ProjectInfo.objects.count() == 1
    assert FunderInfo.objects.count() == 1
    assert FunderIdentifier.objects.count() == 1


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
