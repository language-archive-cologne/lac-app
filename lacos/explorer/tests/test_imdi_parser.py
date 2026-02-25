from lacos.explorer.services.imdi_parser import parse_imdi

EXPECTED_ACTOR_COUNT = 2
EXPECTED_CORPUS_LINK_COUNT = 3

SESSION_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<METATRANSCRIPT xmlns="http://www.mpi.nl/IMDI/Schema/IMDI"
                Type="SESSION" Version="3.0">
  <Session>
    <Name>test_session</Name>
    <Title>Test Session Title</Title>
    <Date>2024-01-15</Date>
    <Description>A test session for unit testing.</Description>
    <MDGroup>
      <Location>
        <Continent>Asia</Continent>
        <Country>Indonesia</Country>
        <Region>Papua</Region>
        <Address>Jayapura</Address>
      </Location>
      <Project>
        <Name>TestProject</Name>
        <Title>The Test Project</Title>
        <Contact>
          <Name>Dr. Tester</Name>
        </Contact>
      </Project>
      <Content>
        <Genre>Narrative</Genre>
        <CommunicationContext>
          <Interactivity>interactive</Interactivity>
          <PlanningType>semi-spontaneous</PlanningType>
        </CommunicationContext>
      </Content>
      <Actors>
        <Actor>
          <Role>Speaker</Role>
          <Name>Speaker One</Name>
          <Sex>Male</Sex>
          <Age>45</Age>
          <BirthDate>1979-03-12</BirthDate>
          <EthnicGroup>Papuan</EthnicGroup>
        </Actor>
        <Actor>
          <Role>Researcher</Role>
          <Name>Dr. Tester</Name>
          <Sex>Female</Sex>
          <Age>38</Age>
        </Actor>
      </Actors>
    </MDGroup>
    <Resources>
      <MediaFile>
        <ResourceLink>test_session.wav</ResourceLink>
        <Type>audio</Type>
        <Format>audio/x-wav</Format>
        <Size>1024000</Size>
      </MediaFile>
      <WrittenResource>
        <ResourceLink>test_session.eaf</ResourceLink>
        <Type>Annotation</Type>
        <Format>text/x-eaf+xml</Format>
        <Size>50000</Size>
      </WrittenResource>
    </Resources>
  </Session>
</METATRANSCRIPT>
"""


CORPUS_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<METATRANSCRIPT xmlns="http://www.mpi.nl/IMDI/Schema/IMDI"
                Type="CORPUS" Version="3.0">
  <Corpus>
    <Name>TestCorpus</Name>
    <Title>Test Corpus Title</Title>
    <Description>Top-level corpus for testing.</Description>
    <CorpusLink Name="SubCorpus1">subcorpus1/subcorpus1.imdi</CorpusLink>
    <CorpusLink Name="Session1">sessions/session1.imdi</CorpusLink>
    <CorpusLink Name="Session2">sessions/session2.imdi</CorpusLink>
  </Corpus>
</METATRANSCRIPT>
"""

CATALOGUE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<METATRANSCRIPT xmlns="http://www.mpi.nl/IMDI/Schema/IMDI"
                Type="CATALOGUE" Version="3.0">
  <Catalogue>
    <Name>DemoCatalogue</Name>
    <Title>Catalogue Title</Title>
    <Description>Catalogue description.</Description>
    <Publisher>LAC</Publisher>
  </Catalogue>
</METATRANSCRIPT>
"""

CUSTOM_FIELDS_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<METATRANSCRIPT xmlns="http://www.mpi.nl/IMDI/Schema/IMDI"
                Type="SESSION" Version="3.0">
  <Session>
    <Name>session_with_custom_fields</Name>
    <MDGroup>
      <Keys>
        <Key Name="Orthography">IPA</Key>
      </Keys>
    </MDGroup>
  </Session>
</METATRANSCRIPT>
"""


def test_parse_session_returns_root_node():
    root = parse_imdi(SESSION_XML)
    assert root is not None
    assert root.node_type == "Session"
    assert root.label == "test_session"


def test_parse_session_metadata_fields():
    root = parse_imdi(SESSION_XML)
    assert root is not None
    assert root.metadata["Title"] == "Test Session Title"
    assert root.metadata["Date"] == "2024-01-15"
    assert root.metadata["Description"] == "A test session for unit testing."


def test_parse_session_location():
    root = parse_imdi(SESSION_XML)
    assert root is not None
    location = next(child for child in root.children if child.node_type == "Location")
    assert location.metadata["Country"] == "Indonesia"
    assert location.metadata["Region"] == "Papua"


def test_parse_session_actors():
    root = parse_imdi(SESSION_XML)
    assert root is not None
    actors = [child for child in root.children if child.node_type == "Actor"]
    assert len(actors) == EXPECTED_ACTOR_COUNT
    assert actors[0].label == "Speaker One"
    assert actors[0].metadata["Role"] == "Speaker"
    assert actors[0].metadata["Sex"] == "Male"


def test_parse_session_resources():
    root = parse_imdi(SESSION_XML)
    assert root is not None
    media_files = [child for child in root.children if child.node_type == "MediaFile"]
    written_resources = [
        child for child in root.children if child.node_type == "WrittenResource"
    ]
    assert len(media_files) == 1
    assert media_files[0].label == "test_session.wav"
    assert media_files[0].metadata["Format"] == "audio/x-wav"
    assert len(written_resources) == 1
    assert written_resources[0].label == "test_session.eaf"


def test_parse_session_project():
    root = parse_imdi(SESSION_XML)
    assert root is not None
    project = next(child for child in root.children if child.node_type == "Project")
    assert project.metadata["Name"] == "TestProject"
    assert project.metadata["Title"] == "The Test Project"


def test_parse_session_content():
    root = parse_imdi(SESSION_XML)
    assert root is not None
    content = next(child for child in root.children if child.node_type == "Content")
    assert content.metadata["Genre"] == "Narrative"


def test_parse_corpus_returns_root_node():
    root = parse_imdi(CORPUS_XML)
    assert root is not None
    assert root.node_type == "Corpus"
    assert root.label == "TestCorpus"


def test_parse_corpus_metadata():
    root = parse_imdi(CORPUS_XML)
    assert root is not None
    assert root.metadata["Title"] == "Test Corpus Title"
    assert root.metadata["Description"] == "Top-level corpus for testing."


def test_parse_corpus_links():
    root = parse_imdi(CORPUS_XML)
    assert root is not None
    links = [child for child in root.children if child.node_type == "CorpusLink"]
    assert len(links) == EXPECTED_CORPUS_LINK_COUNT
    assert links[0].label == "SubCorpus1"
    assert links[0].corpus_link == "subcorpus1/subcorpus1.imdi"
    assert links[1].label == "Session1"


def test_parse_invalid_xml_returns_none():
    result = parse_imdi(b"<not valid xml")
    assert result is None


def test_parse_empty_metatranscript_returns_none():
    xml = b"""\
    <?xml version="1.0"?>
    <METATRANSCRIPT xmlns="http://www.mpi.nl/IMDI/Schema/IMDI" Type="SESSION">
    </METATRANSCRIPT>
    """
    result = parse_imdi(xml)
    assert result is None


def test_parse_catalogue_returns_root_node():
    root = parse_imdi(CATALOGUE_XML)
    assert root is not None
    assert root.node_type == "Catalogue"
    assert root.label == "DemoCatalogue"
    assert root.metadata["Title"] == "Catalogue Title"
    assert root.metadata["Publisher"] == "LAC"


def test_parse_custom_fields_maps_key_nodes():
    root = parse_imdi(CUSTOM_FIELDS_XML)
    assert root is not None
    keys_node = next(child for child in root.children if child.node_type == "Keys")
    key_node = next(child for child in keys_node.children if child.node_type == "Key")
    assert key_node.metadata["@Name"] == "Orthography"
    assert key_node.metadata["Value"] == "IPA"
