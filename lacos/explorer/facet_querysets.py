"""Base querysets shared by faceted-search views and cache warming."""

from django.contrib.contenttypes.models import ContentType
from django.db.models import CharField
from django.db.models import OuterRef
from django.db.models import QuerySet
from django.db.models import Subquery
from django.db.models.functions import Cast

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.storage.models.acl_permissions import ACLPermissions


def collection_facet_queryset() -> QuerySet[Collection]:
    return _with_acl_access_level(Collection.objects.all(), Collection)


def bundle_facet_queryset() -> QuerySet[Bundle]:
    return _with_acl_access_level(Bundle.objects.all(), Bundle)


def _with_acl_access_level(queryset: QuerySet, model: type) -> QuerySet:
    content_type = ContentType.objects.get_for_model(model)
    return queryset.annotate(
        acl_access_level=Subquery(
            ACLPermissions.objects.filter(
                content_type=content_type,
                object_id=Cast(OuterRef("pk"), output_field=CharField()),
            ).values("access_level")[:1],
        ),
    )
