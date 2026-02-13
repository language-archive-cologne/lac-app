"""
Search indexing service for building and updating search vectors.

This module provides functions to compute and store search vectors for
Collection and Bundle models, enabling fast full-text search with PostgreSQL.
"""
from __future__ import annotations

from django.contrib.postgres.search import SearchVector
from django.db.models import Value

from lacos.blam.models import Bundle, Collection


def build_collection_search_vector(collection: Collection) -> SearchVector:
    """Build a SearchVector for a single collection."""
    vectors = []

    # Identifier (weight A)
    vectors.append(SearchVector(Value(collection.identifier or ""), weight="A", config="simple"))

    # General info fields
    general_info = collection.general_info.first()
    if general_info:
        # Display title (weight A)
        vectors.append(SearchVector(Value(general_info.display_title or ""), weight="A", config="simple"))
        # Description (weight B)
        vectors.append(SearchVector(Value(general_info.description or ""), weight="B", config="simple"))

        # Keywords (weight B)
        for keyword in general_info.keywords.all():
            vectors.append(SearchVector(Value(keyword.value or ""), weight="B", config="simple"))

        # Object languages (weight C)
        for lang in general_info.object_languages.all():
            vectors.append(SearchVector(Value(lang.name or ""), weight="C", config="simple"))
            vectors.append(SearchVector(Value(lang.display_name or ""), weight="C", config="simple"))
            # Alternative names
            for alt_name in lang.alternative_names.all():
                vectors.append(SearchVector(Value(alt_name.value or ""), weight="C", config="simple"))
            # Language family
            if hasattr(lang, 'taxonomy') and lang.taxonomy:
                for family in lang.taxonomy.language_family.all():
                    vectors.append(SearchVector(Value(family.value or ""), weight="C", config="simple"))

        # Location (weight D)
        if general_info.location:
            loc = general_info.location
            vectors.append(SearchVector(Value(loc.location_name or ""), weight="D", config="simple"))
            vectors.append(SearchVector(Value(loc.location_facet or ""), weight="D", config="simple"))
            vectors.append(SearchVector(Value(loc.region_facet or ""), weight="D", config="simple"))
            vectors.append(SearchVector(Value(loc.country_name or ""), weight="D", config="simple"))
            vectors.append(SearchVector(Value(loc.country_facet or ""), weight="D", config="simple"))

    # Publication info
    pub_info = collection.publication_info.first()
    if pub_info:
        # Creators (weight C)
        for creator in pub_info.creators.all():
            vectors.append(SearchVector(Value(creator.family_name or ""), weight="C", config="simple"))
        # Contributors (weight D)
        for contributor in pub_info.contributors.all():
            vectors.append(SearchVector(Value(contributor.family_name or ""), weight="D", config="simple"))
        # Data provider (weight D)
        vectors.append(SearchVector(Value(pub_info.data_provider or ""), weight="D", config="simple"))

    # Project info (weight D)
    for project in collection.project_infos.all():
        vectors.append(SearchVector(Value(project.project_display_name or ""), weight="D", config="simple"))
        for funder in project.funder_infos.all():
            vectors.append(SearchVector(Value(funder.grant_identifier or ""), weight="D", config="simple"))

    # Combine all vectors
    if not vectors:
        return SearchVector(Value(""), config="simple")

    result = vectors[0]
    for v in vectors[1:]:
        result = result + v
    return result


def build_bundle_search_vector(bundle: Bundle) -> SearchVector:
    """Build a SearchVector for a single bundle."""
    vectors = []

    # Identifier (weight A)
    vectors.append(SearchVector(Value(bundle.identifier or ""), weight="A", config="simple"))

    # General info fields
    general_info = bundle.general_info.first()
    if general_info:
        # Display title (weight A)
        vectors.append(SearchVector(Value(general_info.display_title or ""), weight="A", config="simple"))
        # Description (weight B)
        vectors.append(SearchVector(Value(general_info.description or ""), weight="B", config="simple"))

        # Keywords (weight C)
        for keyword in general_info.keywords.all():
            vectors.append(SearchVector(Value(keyword.value or ""), weight="C", config="simple"))

        # Object languages (weight C)
        for lang in general_info.object_languages.all():
            vectors.append(SearchVector(Value(lang.name or ""), weight="C", config="simple"))
            vectors.append(SearchVector(Value(lang.display_name or ""), weight="C", config="simple"))
            # Alternative names
            for alt_name in lang.alternative_names.all():
                vectors.append(SearchVector(Value(alt_name.value or ""), weight="C", config="simple"))
            # Language family
            if hasattr(lang, 'bundle_object_language_taxonomy') and lang.bundle_object_language_taxonomy:
                for family in lang.bundle_object_language_taxonomy.language_family.all():
                    vectors.append(SearchVector(Value(family.value or ""), weight="C", config="simple"))

        # Location (weight D)
        if general_info.location:
            loc = general_info.location
            vectors.append(SearchVector(Value(loc.location_facet or ""), weight="D", config="simple"))
            vectors.append(SearchVector(Value(loc.region_facet or ""), weight="D", config="simple"))
            vectors.append(SearchVector(Value(loc.country_facet or ""), weight="D", config="simple"))

    # Structural info
    structural_info = bundle.structural_info.first()
    if structural_info:
        # Bundle topics (weight B)
        for topic in structural_info.bundle_topics.all():
            vectors.append(SearchVector(Value(topic.name or ""), weight="B", config="simple"))

        # Parent collection (weight D)
        if structural_info.is_member_of_collection:
            parent = structural_info.is_member_of_collection
            vectors.append(SearchVector(Value(parent.identifier or ""), weight="D", config="simple"))
            parent_general = parent.general_info.first()
            if parent_general:
                vectors.append(SearchVector(Value(parent_general.display_title or ""), weight="D", config="simple"))

    # Project info (weight D)
    for project in bundle.projects.all():
        vectors.append(SearchVector(Value(project.project_display_name or ""), weight="D", config="simple"))
        for funder in project.funder_infos.all():
            vectors.append(SearchVector(Value(funder.grant_identifier or ""), weight="D", config="simple"))

    # Combine all vectors
    if not vectors:
        return SearchVector(Value(""), config="simple")

    result = vectors[0]
    for v in vectors[1:]:
        result = result + v
    return result


def update_collection_search_vector(collection: Collection) -> None:
    """Update the search vector for a collection and save it."""
    from django.db import connection

    # We need to execute this as a raw SQL update because Django's ORM
    # doesn't handle SearchVector assignment directly
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE blam_collection
            SET search_vector = (
                SELECT
                    setweight(to_tsvector('simple', COALESCE(c.identifier, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(gi.display_title, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(gi.description, '')), 'B') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT kw.value, ' '), '')), 'B') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT ol.name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT ol.display_name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT olan.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT lf.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT cr.family_name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT co.family_name, ' '), '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(pi.data_provider, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.location_name, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.location_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.region_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.country_name, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.country_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT proj.project_display_name, ' '), '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT fi.grant_identifier, ' '), '')), 'D')
                FROM blam_collection c
                LEFT JOIN blam_collectiongeneralinfo gi ON gi.collection_id = c.id
                LEFT JOIN blam_collectiongeneralinfo_keywords gik ON gik.collectiongeneralinfo_id = gi.id
                LEFT JOIN blam_collectionkeyword kw ON kw.id = gik.collectionkeyword_id
                LEFT JOIN blam_collectiongeneralinfo_object_languages giol ON giol.collectiongeneralinfo_id = gi.id
                LEFT JOIN blam_collectionobjectlanguage ol ON ol.id = giol.collectionobjectlanguage_id
                LEFT JOIN blam_collectionobjectlanguage_alternative_names olans ON olans.collectionobjectlanguage_id = ol.id
                LEFT JOIN blam_collectionobjectlanguagealternativename olan ON olan.id = olans.collectionobjectlanguagealternativename_id
                LEFT JOIN blam_collectionobjectlanguagetaxonomy olt ON olt.object_language_id = ol.id
                LEFT JOIN blam_collectionobjectlanguagetaxonomy_language_family oltlf ON oltlf.collectionobjectlanguagetaxonomy_id = olt.id
                LEFT JOIN blam_collectionobjectlanguagelanguagefamily lf ON lf.id = oltlf.collectionobjectlanguagelanguagefamily_id
                LEFT JOIN blam_collectionlocation loc ON loc.id = gi.location_id
                LEFT JOIN blam_collectionpublicationinfo pi ON pi.collection_id = c.id
                LEFT JOIN blam_collectionpublicationinfo_creators pic ON pic.collectionpublicationinfo_id = pi.id
                LEFT JOIN blam_collectioncreator cr ON cr.id = pic.collectioncreator_id
                LEFT JOIN blam_collectionpublicationinfo_contributors pico ON pico.collectionpublicationinfo_id = pi.id
                LEFT JOIN blam_collectioncontributor co ON co.id = pico.collectioncontributor_id
                LEFT JOIN blam_collection_project_infos cpi ON cpi.collection_id = c.id
                LEFT JOIN blam_projectinfo proj ON proj.id = cpi.projectinfo_id
                LEFT JOIN blam_projectinfo_funder_infos pfi ON pfi.projectinfo_id = proj.id
                LEFT JOIN blam_funderinfo fi ON fi.id = pfi.funderinfo_id
                WHERE c.id = %s
                GROUP BY c.id, gi.id, pi.id, loc.id
            )
            WHERE id = %s
            """,
            [str(collection.id), str(collection.id)]
        )


def update_bundle_search_vector(bundle: Bundle) -> None:
    """Update the search vector for a bundle and save it."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE blam_bundle
            SET search_vector = (
                SELECT
                    setweight(to_tsvector('simple', COALESCE(b.identifier, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(gi.display_title, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(gi.description, '')), 'B') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT bt.name, ' '), '')), 'B') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT kw.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT ol.name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT ol.display_name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT olan.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT lf.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(loc.location_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.region_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.country_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT proj.project_display_name, ' '), '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT fi.grant_identifier, ' '), '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(pc.identifier, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(pcgi.display_title, '')), 'D')
                FROM blam_bundle b
                LEFT JOIN blam_bundlegeneralinfo gi ON gi.bundle_id = b.id
                LEFT JOIN blam_bundlegeneralinfo_keywords gik ON gik.bundlegeneralinfo_id = gi.id
                LEFT JOIN blam_bundlekeyword kw ON kw.id = gik.bundlekeyword_id
                LEFT JOIN blam_bundlegeneralinfo_object_languages giol ON giol.bundlegeneralinfo_id = gi.id
                LEFT JOIN blam_bundleobjectlanguage ol ON ol.id = giol.bundleobjectlanguage_id
                LEFT JOIN blam_bundleobjectlanguage_alternative_names olans ON olans.bundleobjectlanguage_id = ol.id
                LEFT JOIN blam_bundleobjectlanguagealternativename olan ON olan.id = olans.bundleobjectlanguagealternativename_id
                LEFT JOIN blam_bundleobjectlanguagetaxonomy olt ON olt.object_language_id = ol.id
                LEFT JOIN blam_bundleobjectlanguagetaxonomy_language_family oltlf ON oltlf.bundleobjectlanguagetaxonomy_id = olt.id
                LEFT JOIN blam_bundleobjectlanguagelanguagefamily lf ON lf.id = oltlf.bundleobjectlanguagelanguagefamily_id
                LEFT JOIN blam_bundlelocation loc ON loc.id = gi.location_id
                LEFT JOIN blam_bundlestructuralinfo si ON si.bundle_id = b.id
                LEFT JOIN blam_bundlestructuralinfo_bundle_topics sibt ON sibt.bundlestructuralinfo_id = si.id
                LEFT JOIN blam_bundletopic bt ON bt.id = sibt.bundletopic_id
                LEFT JOIN blam_collection pc ON pc.id = si.is_member_of_collection_id
                LEFT JOIN blam_collectiongeneralinfo pcgi ON pcgi.collection_id = pc.id
                LEFT JOIN blam_bundle_projects bp ON bp.bundle_id = b.id
                LEFT JOIN blam_projectinfo proj ON proj.id = bp.projectinfo_id
                LEFT JOIN blam_projectinfo_funder_infos pfi ON pfi.projectinfo_id = proj.id
                LEFT JOIN blam_funderinfo fi ON fi.id = pfi.funderinfo_id
                WHERE b.id = %s
                GROUP BY b.id, gi.id, loc.id, si.id, pc.id, pcgi.id
            )
            WHERE id = %s
            """,
            [str(bundle.id), str(bundle.id)]
        )


def rebuild_all_search_vectors() -> tuple[int, int]:
    """Rebuild search vectors for all collections and bundles."""
    from django.db import connection

    # Update all collections
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE blam_collection c
            SET search_vector = subq.sv
            FROM (
                SELECT
                    c.id,
                    setweight(to_tsvector('simple', COALESCE(c.identifier, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(gi.display_title, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(gi.description, '')), 'B') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT kw.value, ' '), '')), 'B') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT ol.name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT ol.display_name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT olan.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT lf.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT cr.family_name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT co.family_name, ' '), '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(pi.data_provider, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.location_name, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.location_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.region_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.country_name, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.country_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT proj.project_display_name, ' '), '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT fi.grant_identifier, ' '), '')), 'D')
                    AS sv
                FROM blam_collection c
                LEFT JOIN blam_collectiongeneralinfo gi ON gi.collection_id = c.id
                LEFT JOIN blam_collectiongeneralinfo_keywords gik ON gik.collectiongeneralinfo_id = gi.id
                LEFT JOIN blam_collectionkeyword kw ON kw.id = gik.collectionkeyword_id
                LEFT JOIN blam_collectiongeneralinfo_object_languages giol ON giol.collectiongeneralinfo_id = gi.id
                LEFT JOIN blam_collectionobjectlanguage ol ON ol.id = giol.collectionobjectlanguage_id
                LEFT JOIN blam_collectionobjectlanguage_alternative_names olans ON olans.collectionobjectlanguage_id = ol.id
                LEFT JOIN blam_collectionobjectlanguagealternativename olan ON olan.id = olans.collectionobjectlanguagealternativename_id
                LEFT JOIN blam_collectionobjectlanguagetaxonomy olt ON olt.object_language_id = ol.id
                LEFT JOIN blam_collectionobjectlanguagetaxonomy_language_family oltlf ON oltlf.collectionobjectlanguagetaxonomy_id = olt.id
                LEFT JOIN blam_collectionobjectlanguagelanguagefamily lf ON lf.id = oltlf.collectionobjectlanguagelanguagefamily_id
                LEFT JOIN blam_collectionlocation loc ON loc.id = gi.location_id
                LEFT JOIN blam_collectionpublicationinfo pi ON pi.collection_id = c.id
                LEFT JOIN blam_collectionpublicationinfo_creators pic ON pic.collectionpublicationinfo_id = pi.id
                LEFT JOIN blam_collectioncreator cr ON cr.id = pic.collectioncreator_id
                LEFT JOIN blam_collectionpublicationinfo_contributors pico ON pico.collectionpublicationinfo_id = pi.id
                LEFT JOIN blam_collectioncontributor co ON co.id = pico.collectioncontributor_id
                LEFT JOIN blam_collection_project_infos cpi ON cpi.collection_id = c.id
                LEFT JOIN blam_projectinfo proj ON proj.id = cpi.projectinfo_id
                LEFT JOIN blam_projectinfo_funder_infos pfi ON pfi.projectinfo_id = proj.id
                LEFT JOIN blam_funderinfo fi ON fi.id = pfi.funderinfo_id
                GROUP BY c.id, gi.id, pi.id, loc.id
            ) subq
            WHERE c.id = subq.id
            """
        )
        collections_updated = cursor.rowcount

    # Update all bundles
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE blam_bundle b
            SET search_vector = subq.sv
            FROM (
                SELECT
                    b.id,
                    setweight(to_tsvector('simple', COALESCE(b.identifier, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(gi.display_title, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(gi.description, '')), 'B') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT bt.name, ' '), '')), 'B') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT kw.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT ol.name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT ol.display_name, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT olan.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT lf.value, ' '), '')), 'C') ||
                    setweight(to_tsvector('simple', COALESCE(loc.location_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.region_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(loc.country_facet, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT proj.project_display_name, ' '), '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(string_agg(DISTINCT fi.grant_identifier, ' '), '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(pc.identifier, '')), 'D') ||
                    setweight(to_tsvector('simple', COALESCE(pcgi.display_title, '')), 'D')
                    AS sv
                FROM blam_bundle b
                LEFT JOIN blam_bundlegeneralinfo gi ON gi.bundle_id = b.id
                LEFT JOIN blam_bundlegeneralinfo_keywords gik ON gik.bundlegeneralinfo_id = gi.id
                LEFT JOIN blam_bundlekeyword kw ON kw.id = gik.bundlekeyword_id
                LEFT JOIN blam_bundlegeneralinfo_object_languages giol ON giol.bundlegeneralinfo_id = gi.id
                LEFT JOIN blam_bundleobjectlanguage ol ON ol.id = giol.bundleobjectlanguage_id
                LEFT JOIN blam_bundleobjectlanguage_alternative_names olans ON olans.bundleobjectlanguage_id = ol.id
                LEFT JOIN blam_bundleobjectlanguagealternativename olan ON olan.id = olans.bundleobjectlanguagealternativename_id
                LEFT JOIN blam_bundleobjectlanguagetaxonomy olt ON olt.object_language_id = ol.id
                LEFT JOIN blam_bundleobjectlanguagetaxonomy_language_family oltlf ON oltlf.bundleobjectlanguagetaxonomy_id = olt.id
                LEFT JOIN blam_bundleobjectlanguagelanguagefamily lf ON lf.id = oltlf.bundleobjectlanguagelanguagefamily_id
                LEFT JOIN blam_bundlelocation loc ON loc.id = gi.location_id
                LEFT JOIN blam_bundlestructuralinfo si ON si.bundle_id = b.id
                LEFT JOIN blam_bundlestructuralinfo_bundle_topics sibt ON sibt.bundlestructuralinfo_id = si.id
                LEFT JOIN blam_bundletopic bt ON bt.id = sibt.bundletopic_id
                LEFT JOIN blam_collection pc ON pc.id = si.is_member_of_collection_id
                LEFT JOIN blam_collectiongeneralinfo pcgi ON pcgi.collection_id = pc.id
                LEFT JOIN blam_bundle_projects bp ON bp.bundle_id = b.id
                LEFT JOIN blam_projectinfo proj ON proj.id = bp.projectinfo_id
                LEFT JOIN blam_projectinfo_funder_infos pfi ON pfi.projectinfo_id = proj.id
                LEFT JOIN blam_funderinfo fi ON fi.id = pfi.funderinfo_id
                GROUP BY b.id, gi.id, loc.id, si.id, pc.id, pcgi.id
            ) subq
            WHERE b.id = subq.id
            """
        )
        bundles_updated = cursor.rowcount

    return collections_updated, bundles_updated
