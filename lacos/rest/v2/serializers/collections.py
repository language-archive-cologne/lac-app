from lacos.blam.serializers.jsonld import CollectionJsonLdSerializer


def serialize_collection_list_item(collection) -> dict:
    general_info = collection.general_info.first()
    admin_info = collection.administrative_info.first()

    data = {
        "@type": "BLAMCollectionRepository",
        "@id": collection.identifier or str(collection.id),
        "uuid": str(collection.id),
    }

    if general_info:
        data["title"] = general_info.display_title
        data["description"] = general_info.description
        keywords = list(general_info.keywords.values_list("value", flat=True))
        if keywords:
            data["keywords"] = keywords
        languages = list(
            general_info.object_languages.values_list("display_name", flat=True)
        )
        if languages:
            data["languages"] = languages

    if admin_info:
        data["access_level"] = admin_info.access_level

    return data


def serialize_collection_detail(collection) -> dict:
    serializer = CollectionJsonLdSerializer(collection)
    data = serializer.serialize()
    data["uuid"] = str(collection.id)
    return data
