from lacos.blam.serializers.jsonld import BundleJsonLdSerializer


def serialize_bundle_list_item(bundle) -> dict:
    general_info = bundle.general_info.first()
    admin_info = bundle.administrative_info.first()
    structural_info = bundle.structural_info.first()

    data = {
        "@type": "BLAMBundleRepository",
        "@id": bundle.identifier or str(bundle.id),
        "uuid": str(bundle.id),
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

    if structural_info and structural_info.is_member_of_collection:
        col = structural_info.is_member_of_collection
        col_gi = col.general_info.first()
        data["collection"] = {
            "@id": col.identifier or str(col.id),
            "title": col_gi.display_title if col_gi else None,
        }

    return data


def serialize_bundle_detail(bundle) -> dict:
    serializer = BundleJsonLdSerializer(bundle)
    data = serializer.serialize()
    data["uuid"] = str(bundle.id)
    return data
