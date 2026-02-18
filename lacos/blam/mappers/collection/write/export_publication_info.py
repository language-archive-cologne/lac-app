"""Export collection publication info to BLAM schema."""

from typing import Optional

from django.db.models import QuerySet
from xsdata.models.datatype import XmlPeriod

from blam_schemas.collection.blam_collection_repository_v1_2 import (
    Cmd,
    CreatorNameIdentifierIdentifierType,
    ContributorNameIdentifierIdentifierType,
)
from lacos.blam.models.base_indentifiers import PersonIdentifierTypeChoices
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
    CollectionCreator,
    CollectionContributor,
)

# Type aliases
PubInfoType = Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo
CreatorsType = Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionCreators
CreatorType = Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionCreators.CollectionCreator
CreatorNameType = Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionCreators.CollectionCreator.CreatorName
CreatorNameIdType = Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionCreators.CollectionCreator.CreatorNameIdentifier
ContributorsType = Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionContributors
ContributorType = Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionContributors.CollectionContributor
ContributorNameType = Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionContributors.CollectionContributor.ContributorName
ContributorNameIdType = Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionContributors.CollectionContributor.ContributorNameIdentifier


def export_publication_info(pub_info: CollectionPublicationInfo, repo) -> None:
    """Export collection publication info to BLAM schema."""
    info = PubInfoType()

    if pub_info.publication_year is not None:
        info.collection_publication_year = XmlPeriod(f"{pub_info.publication_year}")
    info.collection_data_provider = pub_info.data_provider
    info.collection_creators = _export_creators(pub_info.creators.all())

    if pub_info.contributors.exists():
        info.collection_contributors = _export_contributors(pub_info.contributors.all())

    repo.collection_publication_info = info


def _export_creators(creators: QuerySet[CollectionCreator]) -> CreatorsType:
    creators_data = CreatorsType()
    creators_data.collection_creator = [
        _export_creator(creator, idx) for idx, creator in enumerate(creators)
    ]
    return creators_data


def _export_creator(creator: CollectionCreator, order: int) -> CreatorType:
    creator_data = CreatorType()
    creator_data.order = order

    creator_data.creator_name = _export_creator_name(creator)

    if creator.name_identifier:
        creator_data.creator_name_identifier = [
            _export_creator_name_identifier(creator)
        ]

    if creator.affiliation:
        creator_data.creator_affiliation = [creator.affiliation]

    return creator_data


def _export_creator_name(creator: CollectionCreator) -> CreatorNameType:
    name = CreatorNameType()
    name.creator_family_name = creator.family_name
    if creator.given_name:
        name.creator_given_name = creator.given_name
    return name


def _export_creator_name_identifier(creator: CollectionCreator) -> CreatorNameIdType:
    name_id = CreatorNameIdType()
    name_id.value = creator.name_identifier
    name_id.identifier_type = _map_creator_id_type(creator.name_identifier_type)
    return name_id


def _map_creator_id_type(id_type: Optional[str]) -> Optional[CreatorNameIdentifierIdentifierType]:
    normalized_type = _normalize_person_identifier_type(id_type)
    if not normalized_type:
        return None
    mapping = {
        PersonIdentifierTypeChoices.ORCID.value: CreatorNameIdentifierIdentifierType.ORCID,
        PersonIdentifierTypeChoices.ISNI.value: CreatorNameIdentifierIdentifierType.ISNI,
        PersonIdentifierTypeChoices.EMAIL.value: CreatorNameIdentifierIdentifierType.EMAIL,
        PersonIdentifierTypeChoices.OTHER.value: CreatorNameIdentifierIdentifierType.OTHER,
    }
    return mapping.get(normalized_type, CreatorNameIdentifierIdentifierType.OTHER)


def _export_contributors(contributors: QuerySet[CollectionContributor]) -> ContributorsType:
    contributors_data = ContributorsType()
    contributors_data.collection_contributor = [
        _export_contributor(contrib) for contrib in contributors
    ]
    return contributors_data


def _export_contributor(contributor: CollectionContributor) -> ContributorType:
    contrib_data = ContributorType()

    contrib_data.contributor_name = _export_contributor_name(contributor)

    if contributor.name_identifier:
        contrib_data.contributor_name_identifier = [
            _export_contributor_name_identifier(contributor)
        ]

    if contributor.affiliation:
        contrib_data.contributor_affiliation = [contributor.affiliation]

    if contributor.role:
        contrib_data.contributor_role = [contributor.role]

    return contrib_data


def _export_contributor_name(contributor: CollectionContributor) -> ContributorNameType:
    name = ContributorNameType()
    name.contributor_family_name = contributor.family_name
    if contributor.given_name:
        name.contributor_given_name = contributor.given_name
    return name


def _export_contributor_name_identifier(contributor: CollectionContributor) -> ContributorNameIdType:
    name_id = ContributorNameIdType()
    name_id.value = contributor.name_identifier
    name_id.identifier_type = _map_contributor_id_type(contributor.name_identifier_type)
    return name_id


def _map_contributor_id_type(id_type: Optional[str]) -> Optional[ContributorNameIdentifierIdentifierType]:
    normalized_type = _normalize_person_identifier_type(id_type)
    if not normalized_type:
        return None
    mapping = {
        PersonIdentifierTypeChoices.ORCID.value: ContributorNameIdentifierIdentifierType.ORCID,
        PersonIdentifierTypeChoices.ISNI.value: ContributorNameIdentifierIdentifierType.ISNI,
        PersonIdentifierTypeChoices.EMAIL.value: ContributorNameIdentifierIdentifierType.EMAIL,
        PersonIdentifierTypeChoices.OTHER.value: ContributorNameIdentifierIdentifierType.OTHER,
    }
    return mapping.get(normalized_type, ContributorNameIdentifierIdentifierType.OTHER)


def _normalize_person_identifier_type(id_type: Optional[str]) -> Optional[str]:
    """Normalize identifier type tokens to schema-compatible uppercase values."""
    if not id_type:
        return None
    return str(id_type).strip().upper()
