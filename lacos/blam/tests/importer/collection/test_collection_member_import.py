"""Tests for declared collection member import.

Collection membership is declared via ``CollectionHasCollectionMember`` and must be
persisted independently of whether the member bundle's content exists in the active
archive (issue #146).
"""
import pytest

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.tests.importer.collection.test_reindex_metadata_update import (
    _build_collection_xml,
)

_DEFAULT_MEMBER_LINE = (
    '<CollectionHasCollectionMember IdentifierType="Handle">'
    "hdl:test/bundle-001</CollectionHasCollectionMember>"
)


def _member_line(value: str, id_type: str | None) -> str:
    """Render one CollectionHasCollectionMember element (IdentifierType optional)."""
    attr = f' IdentifierType="{id_type}"' if id_type is not None else ""
    return (
        f"\n          <CollectionHasCollectionMember{attr}>"
        f"{value}</CollectionHasCollectionMember>"
    )


def _collection_xml_with_members(
    self_link: str, members: list[tuple[str, str | None]]
) -> str:
    """Build a valid collection XML whose CollectionMembers block holds ``members``.

    ``members`` is a list of ``(value, identifier_type)`` tuples; pass ``None`` for
    the type to omit the ``IdentifierType`` attribute, and an empty ``members`` list
    to render an empty ``CollectionMembers`` block.
    """
    base = _build_collection_xml(
        self_link=self_link,
        creator_affiliation="University of Cologne",
        contributor_affiliation=None,
        keyword="ritual",
        location_name="Cologne",
        identical_uri=None,
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        rights_holder_name="Test Holder",
        rights_holder_identifier="https://isni.org/isni/000000012146438X",
    )
    members_xml = "".join(_member_line(value, id_type) for value, id_type in members)
    return base.replace(f"\n          {_DEFAULT_MEMBER_LINE}", members_xml)


@pytest.mark.django_db
def test_import_persists_declared_members_including_absent_ones():
    xml = _collection_xml_with_members(
        "hdl:test/coll-members",
        [
            ("hdl:test/bundle-present", "Handle"),
            ("hdl:test/bundle-absent", "Handle"),
        ],
    )

    collection = CollectionImporter.import_from_xml(xml)

    structural_info = collection.structural_info.get()
    members = {m.identifier_value: m.identifier_type for m in structural_info.members.all()}

    assert members == {
        "hdl:test/bundle-present": "Handle",
        "hdl:test/bundle-absent": "Handle",
    }


@pytest.mark.django_db
def test_member_without_identifier_type_stores_blank_type():
    xml = _collection_xml_with_members(
        "hdl:test/coll-no-type",
        [("hdl:test/bundle-untyped", None)],
    )

    collection = CollectionImporter.import_from_xml(xml)

    member = collection.structural_info.get().members.get()
    assert member.identifier_value == "hdl:test/bundle-untyped"
    assert member.identifier_type == ""


@pytest.mark.django_db
def test_blank_member_values_are_skipped():
    xml = _collection_xml_with_members(
        "hdl:test/coll-blank",
        [("hdl:test/bundle-real", "Handle"), ("   ", "Handle")],
    )

    collection = CollectionImporter.import_from_xml(xml)

    values = list(
        collection.structural_info.get().members.values_list("identifier_value", flat=True)
    )
    assert values == ["hdl:test/bundle-real"]


@pytest.mark.django_db
def test_empty_members_block_persists_no_members():
    xml = _collection_xml_with_members("hdl:test/coll-empty", [])

    collection = CollectionImporter.import_from_xml(xml)

    assert collection.structural_info.get().members.count() == 0


@pytest.mark.django_db
def test_reimport_replaces_declared_members():
    self_link = "hdl:test/coll-reindex-members"
    CollectionImporter.import_from_xml(
        _collection_xml_with_members(
            self_link,
            [("hdl:test/bundle-a", "Handle"), ("hdl:test/bundle-b", "Handle")],
        )
    )

    collection = CollectionImporter.import_from_xml(
        _collection_xml_with_members(
            self_link,
            [("hdl:test/bundle-a", "Handle"), ("hdl:test/bundle-c", "Handle")],
        ),
        update_existing=True,
    )

    members = set(
        collection.structural_info.get().members.values_list("identifier_value", flat=True)
    )
    assert members == {"hdl:test/bundle-a", "hdl:test/bundle-c"}
