import pytest
from unittest.mock import patch
import os
from datetime import datetime

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.collection.read.import_collection_publication_info import import_publication_info
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
    CollectionCreator,
    CollectionContributor
)
from blam_schemas.collection.blam_collection_repository_v1_0 import (
    CreatorNameIdentifierIdentifierType,
    ContributorNameIdentifierIdentifierType
)


@pytest.fixture
def real_collection_xml():
    """Get the XML content from a real collection file in the data directory."""
    xml_path = os.path.join('data', 'algerien', 'algerien', 'v1', 'content', 'algerien.xml')
    
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        alternate_paths = [
            os.path.join('data', 'algerien', 'v1', 'content', 'algerien.xml'),
            os.path.join('data', 'formatted', 'algerien.xml')
        ]
        for path in alternate_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except FileNotFoundError:
                continue
        
        raise FileNotFoundError(f"Could not find collection XML file at {xml_path} or alternate locations")


@pytest.fixture
def real_cmd_data(real_collection_xml):
    """Parse real collection XML into CMD data"""
    with patch('django.core.exceptions.ValidationError', Exception):
        return CollectionImporter.validate_xml(real_collection_xml)


@pytest.fixture
def mock_creator():
    """Create a mock creator with configurable fields"""
    def create_creator(family_name="Oukafi", given_name="Issak Cheikh", order=1, affiliations=None, identifiers=None):
        creator = type('Creator', (), {
            'creator_name': type('Name', (), {
                'creator_family_name': family_name,
                'creator_given_name': given_name
            })(),
            'order': order,
            'creator_affiliation': affiliations or ["Forschugnsstelle Afrika der Universität zu Köln"],
            'creator_name_identifier': identifiers or []  # Empty in real data
        })
        return creator
    return create_creator


@pytest.fixture
def mock_contributor():
    """Create a mock contributor with configurable fields"""
    def create_contributor(family_name="Lammers", given_name="Lukas", role="Data Steward", affiliations=None, identifiers=None):
        contributor = type('Contributor', (), {
            'contributor_name': type('Name', (), {
                'contributor_family_name': family_name,
                'contributor_given_name': given_name
            })(),
            'contributor_role': role,
            'contributor_affiliation': affiliations or ["FAIR.rdm im SPP2143 \"Entangled Africa\""],
            'contributor_name_identifier': identifiers or [type('Identifier', (), {
                'identifier_type': ContributorNameIdentifierIdentifierType.ORCID,
                'value': '0000-0002-8200-0199'
            })()]
        })
        return contributor
    return create_contributor


@pytest.fixture
def mock_publication_info():
    """Create a mock publication info schema with configurable fields"""
    def create_pub_info(year=2022, data_provider="FAIR.rdm im SPP2143 \"Entangled Africa\"", creators=None, contributors=None):
        pub_info = type('PublicationInfo', (), {
            'collection_publication_year': str(year) if year is not None else None,  # Just use string for year
            'collection_data_provider': data_provider,
            'collection_creators': type('Creators', (), {
                'collection_creator': creators or []
            })() if creators else None,
            'collection_contributors': type('Contributors', (), {
                'collection_contributor': contributors or []
            })() if contributors else None
        })
        return pub_info
    return create_pub_info


@pytest.fixture
def mock_cmd_data(mock_publication_info):
    """Create a mock CMD data with configurable publication info"""
    def create_cmd(pub_info):
        return type('Cmd', (), {
            'components': type('Components', (), {
                'blam_collection_repository_v1_0': type('Repo', (), {
                    'collection_publication_info': pub_info
                })()
            })()
        })()
    return create_cmd


@pytest.mark.django_db
def test_cmd_data_parsing(real_cmd_data):
    """Test that CMD data is correctly parsed from XML"""
    # Get the publication info from CMD data
    pub_info = real_cmd_data.components.blam_collection_repository_v1_0.collection_publication_info
    
    # Verify basic fields
    assert str(pub_info.collection_publication_year) == "2022"  # Convert XmlPeriod to string for comparison
    assert pub_info.collection_data_provider == "FAIR.rdm im SPP2143 \"Entangled Africa\""
    
    # Verify creators
    assert hasattr(pub_info, 'collection_creators')
    assert pub_info.collection_creators is not None
    assert len(pub_info.collection_creators.collection_creator) == 1
    
    # Verify creator data
    creator = pub_info.collection_creators.collection_creator[0]
    assert creator.creator_name.creator_family_name == "Oukafi"
    assert creator.creator_name.creator_given_name == "Issak Cheikh"
    assert creator.creator_affiliation == ["Forschugnsstelle Afrika der Universität zu Köln"]
    # Check that identifier exists but has empty value
    assert len(creator.creator_name_identifier) == 1
    assert creator.creator_name_identifier[0].value == ""
    
    # Verify contributors
    assert hasattr(pub_info, 'collection_contributors')
    assert pub_info.collection_contributors is not None
    assert len(pub_info.collection_contributors.collection_contributor) == 1
    
    # Verify contributor data
    contributor = pub_info.collection_contributors.collection_contributor[0]
    assert contributor.contributor_name.contributor_family_name == "Lammers"
    assert contributor.contributor_name.contributor_given_name == "Lukas"
    assert contributor.contributor_role == ["Data Steward"]
    assert contributor.contributor_affiliation == ["FAIR.rdm im SPP2143 \"Entangled Africa\""]
    assert contributor.contributor_name_identifier[0].value == "0000-0002-8200-0199"


@pytest.mark.django_db
def test_publication_info_data_mapping(real_cmd_data):
    """Test that publication info is mapped correctly from CMD to Django model"""
    # Test import with real data
    pub_info = import_publication_info(real_cmd_data)
    
    # Verify the object was created and fields were set correctly
    assert isinstance(pub_info, CollectionPublicationInfo)
    assert pub_info.publication_year == 2022
    assert pub_info.data_provider == "FAIR.rdm im SPP2143 \"Entangled Africa\""
    
    # Verify creators were created
    assert pub_info.creators.count() == 1
    creator = pub_info.creators.first()
    assert isinstance(creator, CollectionCreator)
    assert creator.family_name == "Oukafi"
    assert creator.given_name == "Issak Cheikh"
    assert creator.affiliation == "Forschugnsstelle Afrika der Universität zu Köln"
    assert not creator.name_identifier  # Empty in XML
    
    # Verify contributors were created
    assert pub_info.contributors.count() == 1
    contributor = pub_info.contributors.first()
    assert isinstance(contributor, CollectionContributor)
    assert contributor.family_name == "Lammers"
    assert contributor.given_name == "Lukas"
    assert contributor.contributor_display_name == "Lukas Lammers"
    assert contributor.affiliation == "FAIR.rdm im SPP2143 \"Entangled Africa\""
    assert contributor.name_identifier == "0000-0002-8200-0199"
    assert contributor.name_identifier_type == "orcid"


@pytest.mark.django_db
def test_get_or_create_behavior(real_cmd_data):
    """Test that importing the same data twice doesn't create duplicates"""
    # First import
    pub_info1 = import_publication_info(real_cmd_data)
    
    # Second import with same data should get existing record
    pub_info2 = import_publication_info(real_cmd_data)
    
    # Should be the same record
    assert pub_info1.pk == pub_info2.pk
    
    # Count should still be 1
    count = CollectionPublicationInfo.objects.count()
    assert count == 1
    
    # Verify related objects weren't duplicated
    assert CollectionCreator.objects.count() == 1
    assert CollectionContributor.objects.count() == 1


@pytest.mark.django_db
def test_multiple_creators(mock_creator, mock_publication_info, mock_cmd_data):
    """Test handling of multiple creators"""
    # Create mock creators with real data structure
    creators = [
        mock_creator(family_name="Oukafi", given_name="Issak Cheikh"),
        mock_creator(family_name="Lammers", given_name="Lukas")
    ]
    
    # Create publication info with multiple creators
    pub_info = mock_publication_info(creators=creators)
    
    # Import and verify
    result = import_publication_info(mock_cmd_data(pub_info))
    assert result.creators.count() == 2
    
    # Verify both creators were created correctly
    creators = result.creators.all()
    assert creators[0].family_name == "Oukafi"
    assert creators[0].given_name == "Issak Cheikh"
    assert creators[0].affiliation == "Forschugnsstelle Afrika der Universität zu Köln"
    assert creators[1].family_name == "Lammers"
    assert creators[1].given_name == "Lukas"
    assert creators[1].affiliation == "Forschugnsstelle Afrika der Universität zu Köln"


@pytest.mark.django_db
def test_creator_identifiers(mock_creator, mock_publication_info, mock_cmd_data):
    """Test handling of creator identifiers"""
    # Create creator with ORCID identifier (like in real data)
    identifiers = [
        type('Identifier', (), {
            'identifier_type': CreatorNameIdentifierIdentifierType.ORCID,
            'value': '0000-0002-8200-0199'
        })()
    ]
    
    # Create creator with identifier
    creator = mock_creator(identifiers=identifiers)
    pub_info = mock_publication_info(creators=[creator])
    
    # Import and verify
    result = import_publication_info(mock_cmd_data(pub_info))
    creator = result.creators.first()
    
    assert creator.name_identifier == '0000-0002-8200-0199'
    assert creator.name_identifier_type == 'orcid'


@pytest.mark.django_db
def test_contributors(mock_contributor, mock_publication_info, mock_cmd_data):
    """Test handling of contributors"""
    # Create mock contributor with real data structure
    contributor = mock_contributor(
        family_name="Lammers",
        given_name="Lukas",
        role="Data Steward",
        affiliations=["FAIR.rdm im SPP2143 \"Entangled Africa\""],
        identifiers=[
            type('Identifier', (), {
                'identifier_type': ContributorNameIdentifierIdentifierType.ORCID,
                'value': '0000-0002-8200-0199'
            })()
        ]
    )
    
    # Create publication info with contributor
    pub_info = mock_publication_info(contributors=[contributor])
    
    # Import and verify
    result = import_publication_info(mock_cmd_data(pub_info))
    assert result.contributors.count() == 1
    
    # Verify contributor was created correctly
    contributor = result.contributors.first()
    assert contributor.family_name == "Lammers"
    assert contributor.given_name == "Lukas"
    assert contributor.contributor_display_name == "Lukas Lammers"
    assert contributor.affiliation == "FAIR.rdm im SPP2143 \"Entangled Africa\""
    assert contributor.name_identifier == '0000-0002-8200-0199'
    assert contributor.name_identifier_type == 'orcid'


@pytest.mark.django_db
def test_missing_data_handling(mock_publication_info, mock_cmd_data):
    """Test handling of missing data"""
    # Create publication info with minimal data
    pub_info = mock_publication_info(
        year=None,
        data_provider=None,
        creators=[],
        contributors=[]
    )
    
    # Import should still work with missing data
    result = import_publication_info(mock_cmd_data(pub_info))
    assert isinstance(result, CollectionPublicationInfo)
    
    # Publication year should be set to current year
    assert result.publication_year == datetime.now().year
    
    # Other fields should be empty
    assert result.data_provider == ""  # Empty string for required field
    assert result.creators.count() == 0
    assert result.contributors.count() == 0 