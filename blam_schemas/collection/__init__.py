# Default exports from v1.2 (latest version)
from blam_schemas.collection.blam_collection_repository_v1_2 import (
    Cmd,
    CollectionHasCollectionMemberIdentifierType,
    CollectionIdIdentifierType,
    ComplextypeAccess41,
    ComplextypeCollectionCountryCode611,
    ComplextypeObjectLanguageGlottologCode0511,
    ComplextypeObjectLanguageIso6393Code0511,
    ContributorNameIdentifierIdentifierType,
    CreatorNameIdentifierIdentifierType,
    FunderIdentifierIdentifierType,
    ResourcetypeSimple,
    RightsHolderIdentifierIdentifierType,
    SimpletypeAccess41,
)

# Legacy v1.0 imports (for backward compatibility)
from blam_schemas.collection.blam_collection_repository_v1_0 import (
    Cmd as CmdV10,
    SimpletypeAccess41 as SimpletypeAccess41V10,
)

# Legacy v1.1 imports (for backward compatibility)
from blam_schemas.collection.blam_collection_repository_v1_1 import (
    BlamCollectionRepositoryV11,
    SimpletypeAccess41 as SimpletypeAccess41V11,
)

from blam_schemas.collection.cmd_envelop import Cmd as EnvelopeCmd, ResourcetypeSimple as EnvelopeResourcetypeSimple

__all__ = [
    # Default (v1.2)
    "Cmd",
    "CollectionHasCollectionMemberIdentifierType",
    "CollectionIdIdentifierType",
    "ComplextypeAccess41",
    "ComplextypeCollectionCountryCode611",
    "ComplextypeObjectLanguageGlottologCode0511",
    "ComplextypeObjectLanguageIso6393Code0511",
    "ContributorNameIdentifierIdentifierType",
    "CreatorNameIdentifierIdentifierType",
    "FunderIdentifierIdentifierType",
    "ResourcetypeSimple",
    "RightsHolderIdentifierIdentifierType",
    "SimpletypeAccess41",
    # Legacy
    "CmdV10",
    "SimpletypeAccess41V10",
    "SimpletypeAccess41V11",
    "BlamCollectionRepositoryV11",
    # Envelope
    "EnvelopeCmd",
    "EnvelopeResourcetypeSimple",
]
