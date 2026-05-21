import pytest

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.collection.write.collection_exporter import CollectionExporter
from lacos.blam.models.base_project_info import (
    FunderIdentifier,
    FunderInfo,
    ProjectInfo,
)
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionIdenticalResource,
    CollectionLicense,
    CollectionRightsHolder,
    CollectionRightsHolderIdentifier,
)
from lacos.blam.models.collection.collection_general_info import (
    CollectionKeyword,
    CollectionLocation,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionContributor,
    CollectionCreator,
    CollectionPublicationInfoCreator,
)


def _build_collection_xml(
    *,
    self_link: str,
    creator_affiliation: str,
    contributor_affiliation: str | None,
    keyword: str | None,
    location_name: str,
    identical_uri: str | None,
    license_name: str,
    license_identifier: str,
    rights_holder_name: str,
    rights_holder_identifier: str,
    project_description: str | None = None,
    funder_name: str | None = None,
    funder_identifier: str | None = None,
    extra_keywords: list[str] | None = None,
    extra_rights_holders: list[tuple[str, str]] | None = None,
    creator_specs: list[dict[str, object]] | None = None,
) -> str:
    project_xml = ""
    if project_description is not None and funder_name is not None and funder_identifier is not None:
        project_xml = f"""
      <ProjectInfo>
        <Project>
          <ProjectDisplayName>Shared Project</ProjectDisplayName>
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

    keywords_xml = ""
    keyword_values = [value for value in [keyword, *(extra_keywords or [])] if value]
    if keyword_values:
        keywords_items = "".join(
            f"\n          <CollectionKeyword>{value}</CollectionKeyword>" for value in keyword_values
        )
        keywords_xml = f"""
        <CollectionKeywords>{keywords_items}
        </CollectionKeywords>"""

    contributors_xml = ""
    if contributor_affiliation is not None:
        contributors_xml = f"""
        <CollectionContributors>
          <CollectionContributor>
            <ContributorNameIdentifier IdentifierType="ISNI">https://isni.org/isni/000000012146438X</ContributorNameIdentifier>
            <ContributorAffiliation>{contributor_affiliation}</ContributorAffiliation>
            <ContributorRole>Editor</ContributorRole>
            <ContributorName>
              <ContributorFamilyName>Taylor</ContributorFamilyName>
              <ContributorGivenName>Mia</ContributorGivenName>
            </ContributorName>
          </CollectionContributor>
        </CollectionContributors>"""

    identical_xml = ""
    if identical_uri is not None:
        identical_xml = f"""
        <CollectionIsIdenticalTo>{identical_uri}</CollectionIsIdenticalTo>"""

    rights_holders = [(rights_holder_name, rights_holder_identifier), *(extra_rights_holders or [])]
    rights_holders_xml = "".join(
        f"""
        <RightsHolder>
          <RightsHolderName>{name}</RightsHolderName>
          <RightsHolderIdentifier IdentifierType="ISNI">{identifier}</RightsHolderIdentifier>
        </RightsHolder>"""
        for name, identifier in rights_holders
    )
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
          <CollectionCreator{f' Order="{spec["order"]}"' if spec.get("order") is not None else ""}>
            <CreatorNameIdentifier IdentifierType="ORCID">{spec.get("identifier", "https://orcid.org/0000-0000-0000-0001")}</CreatorNameIdentifier>
            <CreatorAffiliation>{spec.get("affiliation", creator_affiliation)}</CreatorAffiliation>
            <CreatorName>
              <CreatorFamilyName>{spec["family_name"]}</CreatorFamilyName>
              <CreatorGivenName>{spec["given_name"]}</CreatorGivenName>
            </CreatorName>
          </CollectionCreator>"""
        for spec in creator_specs
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CMD xmlns="http://www.clarin.eu/cmd/">
  <Header>
    <MdCreator>test</MdCreator>
    <MdCreationDate>2024-01-01</MdCreationDate>
    <MdSelfLink>{self_link}</MdSelfLink>
    <MdProfile>clarin.eu:cr1:p_test</MdProfile>
    <MdCollectionDisplayName>Test Collection</MdCollectionDisplayName>
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
{keywords_xml}
        <CollectionObjectLanguages>
          <CollectionObjectLanguage>
            <ObjectLanguageDisplayName>English</ObjectLanguageDisplayName>
            <ObjectLanguageName>English</ObjectLanguageName>
            <ObjectLanguageISO639-3Code>eng</ObjectLanguageISO639-3Code>
            <ObjectLanguageGlottologCode>stan1293</ObjectLanguageGlottologCode>
          </CollectionObjectLanguage>
        </CollectionObjectLanguages>
        <CollectionLocation>
          <CollectionLocationName>{location_name}</CollectionLocationName>
          <CollectionRegionName>North Rhine-Westphalia</CollectionRegionName>
          <CollectionRegionFacet>North Rhine-Westphalia</CollectionRegionFacet>
          <CollectionCountryName>Germany</CollectionCountryName>
          <CollectionCountryFacet>Germany</CollectionCountryFacet>
          <CollectionCountryCode>DE</CollectionCountryCode>
        </CollectionLocation>
      </CollectionGeneralInfo>
      <CollectionPublicationInfo>
        <CollectionPublicationYear>2024</CollectionPublicationYear>
        <CollectionDataProvider>Test Provider</CollectionDataProvider>
        <CollectionCreators>{creators_xml}
        </CollectionCreators>
{contributors_xml}
      </CollectionPublicationInfo>
      <CollectionAdministrativeInfo>
{identical_xml}
        <Access>public</Access>
        <AvailabilityDate>2024-01-01</AvailabilityDate>
        <License>
          <LicenseName>{license_name}</LicenseName>
          <LicenseIdentifier>{license_identifier}</LicenseIdentifier>
        </License>
{rights_holders_xml}
      </CollectionAdministrativeInfo>
      <CollectionStructuralInfo>
        <CollectionMembers>
          <CollectionHasCollectionMember IdentifierType="Handle">hdl:test/bundle-001</CollectionHasCollectionMember>
        </CollectionMembers>
      </CollectionStructuralInfo>{project_xml}
    </BLAM-collection-repository_v1.2>
  </Components>
</CMD>"""


@pytest.mark.django_db
def test_collection_creator_order_uses_xml_element_sequence():
    xml = _build_collection_xml(
        self_link="hdl:test/collection-creator-order-attribute",
        creator_affiliation="University Stable",
        contributor_affiliation=None,
        keyword="keyword-stable",
        location_name="Village Stable",
        identical_uri="https://example.com/collections/identical-stable",
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

    collection = CollectionImporter.import_from_xml(xml)
    publication_info = collection.publication_info.get()

    ordered_links = (
        CollectionPublicationInfoCreator.objects.filter(
            collectionpublicationinfo=publication_info
        )
        .select_related("collectioncreator")
        .order_by("order", "pk")
    )
    assert [
        (link.order, link.collectioncreator.family_name)
        for link in ordered_links
    ] == [
        (0, "ElementFirst"),
        (1, "OrderZero"),
        (2, "OrderOne"),
    ]

    exported_xml = CollectionExporter().export(collection)
    assert exported_xml.index("<CreatorFamilyName>ElementFirst</CreatorFamilyName>") < exported_xml.index(
        "<CreatorFamilyName>OrderZero</CreatorFamilyName>"
    )
    assert exported_xml.index("<CreatorFamilyName>OrderZero</CreatorFamilyName>") < exported_xml.index(
        "<CreatorFamilyName>OrderOne</CreatorFamilyName>"
    )


@pytest.mark.django_db
def test_collection_creator_order_falls_back_to_element_sequence():
    xml = _build_collection_xml(
        self_link="hdl:test/collection-creator-order-fallback",
        creator_affiliation="University Stable",
        contributor_affiliation=None,
        keyword="keyword-stable",
        location_name="Village Stable",
        identical_uri="https://example.com/collections/identical-stable",
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

    collection = CollectionImporter.import_from_xml(xml)
    publication_info = collection.publication_info.get()

    ordered_links = (
        CollectionPublicationInfoCreator.objects.filter(
            collectionpublicationinfo=publication_info
        )
        .select_related("collectioncreator")
        .order_by("order", "pk")
    )
    assert [
        (link.order, link.collectioncreator.family_name)
        for link in ordered_links
    ] == [
        (0, "ElementZero"),
        (1, "ElementOne"),
    ]


@pytest.mark.django_db
def test_collection_reindex_replaces_owned_metadata_and_projects():
    xml_v1 = _build_collection_xml(
        self_link="hdl:test/collection-metadata-001",
        creator_affiliation="University A",
        contributor_affiliation="Institute A",
        keyword="keyword-one",
        location_name="Village One",
        identical_uri="https://example.com/collections/identical-one",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Rights Holder A",
        rights_holder_identifier="https://isni.org/isni/000000012281955X",
        project_description="Original shared project description",
        funder_name="Funder A",
        funder_identifier="https://example.com/funders/a",
    )
    collection = CollectionImporter.import_from_xml(xml_v1)

    xml_v2 = _build_collection_xml(
        self_link="hdl:test/collection-metadata-001",
        creator_affiliation="University B",
        contributor_affiliation="Institute B",
        keyword="keyword-two",
        location_name="Village Two",
        identical_uri="https://example.com/collections/identical-two",
        license_name="CC-BY-SA-4.0",
        license_identifier="https://creativecommons.org/licenses/by-sa/4.0/",
        rights_holder_name="Rights Holder B",
        rights_holder_identifier="https://isni.org/isni/0000000404592786",
        project_description="Updated shared project description",
        funder_name="Funder B",
        funder_identifier="https://example.com/funders/b",
    )
    CollectionImporter.import_from_xml(xml_v2, update_existing=True)

    publication_info = collection.publication_info.get()
    general_info = collection.general_info.get()
    admin_info = collection.administrative_info.get()
    project = collection.project_infos.get()

    creator = publication_info.creators.get()
    contributor = publication_info.contributors.get()
    assert creator.affiliation == "University B"
    assert contributor.affiliation == "Institute B"
    assert CollectionCreator.objects.count() == 1
    assert CollectionContributor.objects.count() == 1

    assert list(general_info.keywords.values_list("value", flat=True)) == ["keyword-two"]
    assert general_info.location.location_name == "Village Two"
    assert CollectionKeyword.objects.count() == 1
    assert CollectionLocation.objects.count() == 1

    assert list(admin_info.is_identical_to.values_list("uri", flat=True)) == [
        "https://example.com/collections/identical-two"
    ]
    assert list(admin_info.licenses.values_list("license_name", flat=True)) == ["CC-BY-SA-4.0"]
    assert list(admin_info.rights_holders.values_list("rights_holder_name", flat=True)) == [
        "Rights Holder B"
    ]
    assert CollectionIdenticalResource.objects.count() == 1
    assert CollectionLicense.objects.count() == 1
    assert CollectionRightsHolder.objects.count() == 1
    assert CollectionRightsHolderIdentifier.objects.count() == 1

    assert project.project_description == "Updated shared project description"
    funder = project.funder_infos.get()
    assert funder.funder_name == "Funder B"
    assert funder.funder_identifiers.get().value == "https://example.com/funders/b"
    assert ProjectInfo.objects.count() == 1
    assert FunderInfo.objects.count() == 1
    assert FunderIdentifier.objects.count() == 1

    xml_v3 = _build_collection_xml(
        self_link="hdl:test/collection-metadata-001",
        creator_affiliation="University B",
        contributor_affiliation="Institute B",
        keyword="keyword-two",
        location_name="Village Two",
        identical_uri="https://example.com/collections/identical-two",
        license_name="CC-BY-SA-4.0",
        license_identifier="https://creativecommons.org/licenses/by-sa/4.0/",
        rights_holder_name="Rights Holder B",
        rights_holder_identifier="https://isni.org/isni/0000000404592786",
    )
    CollectionImporter.import_from_xml(xml_v3, update_existing=True)

    collection.refresh_from_db()
    assert collection.project_infos.count() == 0
    assert ProjectInfo.objects.count() == 0
    assert FunderInfo.objects.count() == 0
    assert FunderIdentifier.objects.count() == 0


@pytest.mark.django_db
def test_collection_reindex_isolates_owned_metadata_between_collections():
    xml_a = _build_collection_xml(
        self_link="hdl:test/collection-metadata-A",
        creator_affiliation="Collection A University",
        contributor_affiliation="Collection A Institute",
        keyword="keyword-a",
        location_name="Village A",
        identical_uri="https://example.com/collections/identical-a",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Shared Rights Holder",
        rights_holder_identifier="https://example.com/holders/a",
        project_description="Project description A",
        funder_name="Funder A",
        funder_identifier="https://example.com/funders/shared",
    )
    collection_a = CollectionImporter.import_from_xml(xml_a)

    xml_b = _build_collection_xml(
        self_link="hdl:test/collection-metadata-B",
        creator_affiliation="Collection B University",
        contributor_affiliation="Collection B Institute",
        keyword="keyword-b",
        location_name="Village B",
        identical_uri="https://example.com/collections/identical-b",
        license_name="CC-BY-SA-4.0",
        license_identifier="https://creativecommons.org/licenses/by-sa/4.0/",
        rights_holder_name="Shared Rights Holder",
        rights_holder_identifier="https://example.com/holders/b",
        project_description="Project description B",
        funder_name="Funder B",
        funder_identifier="https://example.com/funders/shared",
    )
    collection_b = CollectionImporter.import_from_xml(xml_b)

    creator_a = collection_a.publication_info.get().creators.get()
    creator_b = collection_b.publication_info.get().creators.get()
    assert creator_a.affiliation == "Collection A University"
    assert creator_b.affiliation == "Collection B University"
    assert creator_a.pk != creator_b.pk

    contributor_a = collection_a.publication_info.get().contributors.get()
    contributor_b = collection_b.publication_info.get().contributors.get()
    assert contributor_a.affiliation == "Collection A Institute"
    assert contributor_b.affiliation == "Collection B Institute"
    assert contributor_a.pk != contributor_b.pk

    rights_holder_a = collection_a.administrative_info.get().rights_holders.get()
    rights_holder_b = collection_b.administrative_info.get().rights_holders.get()
    assert rights_holder_a.rights_holder_identifiers.get().identifier == "https://example.com/holders/a"
    assert rights_holder_b.rights_holder_identifiers.get().identifier == "https://example.com/holders/b"
    assert rights_holder_a.pk != rights_holder_b.pk

    project_a = collection_a.project_infos.get()
    project_b = collection_b.project_infos.get()
    assert project_a.project_description == "Project description A"
    assert project_b.project_description == "Project description B"
    assert project_a.pk != project_b.pk


@pytest.mark.django_db
def test_collection_reindex_is_idempotent_for_same_xml():
    xml = _build_collection_xml(
        self_link="hdl:test/collection-idempotent-001",
        creator_affiliation="University Stable",
        contributor_affiliation="Institute Stable",
        keyword="keyword-stable",
        location_name="Village Stable",
        identical_uri="https://example.com/collections/identical-stable",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Rights Holder Stable",
        rights_holder_identifier="https://example.com/holders/stable",
        project_description="Stable project",
        funder_name="Stable Funder",
        funder_identifier="https://example.com/funders/stable",
    )
    collection = CollectionImporter.import_from_xml(xml)
    CollectionImporter.import_from_xml(xml, update_existing=True)

    assert collection.publication_info.get().creators.count() == 1
    assert collection.publication_info.get().contributors.count() == 1
    assert collection.general_info.get().keywords.count() == 1
    assert collection.administrative_info.get().rights_holders.count() == 1
    assert collection.project_infos.count() == 1
    assert CollectionCreator.objects.count() == 1
    assert CollectionContributor.objects.count() == 1
    assert CollectionKeyword.objects.count() == 1
    assert CollectionLicense.objects.count() == 1
    assert CollectionRightsHolder.objects.count() == 1
    assert ProjectInfo.objects.count() == 1
    assert FunderInfo.objects.count() == 1
    assert FunderIdentifier.objects.count() == 1


@pytest.mark.django_db
def test_collection_reindex_handles_list_diffs_and_optional_section_removal():
    xml_v1 = _build_collection_xml(
        self_link="hdl:test/collection-list-diff-001",
        creator_affiliation="University A",
        contributor_affiliation="Institute A",
        keyword="keyword-one",
        extra_keywords=["keyword-two"],
        location_name="Village One",
        identical_uri="https://example.com/collections/identical-one",
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Rights Holder A",
        rights_holder_identifier="https://example.com/holders/a",
        extra_rights_holders=[("Rights Holder B", "https://example.com/holders/b")],
    )
    collection = CollectionImporter.import_from_xml(xml_v1)

    xml_v2 = _build_collection_xml(
        self_link="hdl:test/collection-list-diff-001",
        creator_affiliation="University A",
        contributor_affiliation=None,
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
    CollectionImporter.import_from_xml(xml_v2, update_existing=True)

    general_info = collection.general_info.get()
    publication_info = collection.publication_info.get()
    admin_info = collection.administrative_info.get()

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
    assert CollectionKeyword.objects.count() == 2
    assert CollectionContributor.objects.count() == 0
    assert CollectionIdenticalResource.objects.count() == 0
    assert CollectionRightsHolder.objects.count() == 2
    assert CollectionRightsHolderIdentifier.objects.count() == 2
