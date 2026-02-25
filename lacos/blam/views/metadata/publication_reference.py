from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from lacos.blam.forms.metadata import reference as reference_forms
from lacos.blam.models.bundle.bundle_publication_info import BundleCreator, BundleContributor, BundlePublicationInfo
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_publication_info import (
    CollectionContributor,
    CollectionCreator,
    CollectionPublicationInfo,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.views.metadata.base import apply_audit_fields
from lacos.common.mixins import HtmxTemplateHelperMixin
from lacos.storage.permissions import can_manage_bundle, can_manage_collection


COLLECTION_PUBLICATION_REFERENCE_CONFIG = {
    "creators": {
        "model": CollectionCreator,
        "form": reference_forms.CollectionCreatorForm,
        "title": "Collection creators",
        "fields": ["family_name", "given_name", "name_identifier"],
        "relation": "creators",
        "item_label": "Creator",
    },
    "contributors": {
        "model": CollectionContributor,
        "form": reference_forms.CollectionContributorForm,
        "title": "Collection contributors",
        "fields": ["family_name", "given_name", "contributor_display_name"],
        "relation": "contributors",
        "item_label": "Contributor",
    },
}

BUNDLE_PUBLICATION_REFERENCE_CONFIG = {
    "creators": {
        "model": BundleCreator,
        "form": reference_forms.BundleCreatorForm,
        "title": "Bundle creators",
        "fields": ["family_name", "given_name", "name_identifier"],
        "relation": "creators",
        "item_label": "Creator",
    },
    "contributors": {
        "model": BundleContributor,
        "form": reference_forms.BundleContributorForm,
        "title": "Bundle contributors",
        "fields": ["family_name", "given_name", "contributor_name"],
        "relation": "contributors",
        "item_label": "Contributor",
    },
}


class BasePublicationReferenceView(HtmxTemplateHelperMixin, View):
    template_name = "blam/metadata/partials/publication_reference_panel.html"
    reference_config: dict[str, dict] = {}
    parent_model = None
    publication_model = None
    publication_lookup = ""
    parent_kwarg = ""
    panel_prefix = ""
    panel_url_name = ""
    edit_url_name = ""
    remove_url_name = ""
    info_label = "publication info"
    use_parent_as_info = False
    auto_create_info = False

    def get_reference_config(self, reference_slug: str) -> dict:
        config = self.reference_config.get(reference_slug)
        if not config:
            raise Http404("Unknown reference type")
        return config

    def _resolve_collection_targets(self, obj) -> list[Collection]:
        if obj is None:
            return []

        if isinstance(obj, Collection):
            return [obj]

        if isinstance(obj, Bundle):
            collection = None
            structural = getattr(obj, "structural_info", None)
            if structural:
                struct_info = structural.first()
                if struct_info:
                    collection = getattr(struct_info, "is_member_of_collection", None)
            return [collection] if collection else []

        direct_collection = getattr(obj, "collection", None)
        if direct_collection:
            return [direct_collection]

        direct_bundle = getattr(obj, "bundle", None)
        if direct_bundle:
            return self._resolve_collection_targets(direct_bundle)

        from lacos.blam.models.base_project_info import ProjectInfo, FunderInfo
        from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleObjectLanguage
        from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionObjectLanguage
        from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo, CollectionRightsHolder
        from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo, BundleRightsHolder
        from lacos.blam.models.bundle.bundle_structural_info import BundleResources, WrittenResource

        if isinstance(obj, ProjectInfo):
            collections = list(obj.collections.all())
            bundles = list(obj.bundles.all())
            for bundle in bundles:
                collections.extend(self._resolve_collection_targets(bundle))
            return [c for c in collections if c]

        if isinstance(obj, FunderInfo):
            collections = []
            for project in obj.projects.all():
                collections.extend(self._resolve_collection_targets(project))
            return [c for c in collections if c]

        if isinstance(obj, WrittenResource):
            resources = BundleResources.objects.filter(bundle_written_resources=obj)
            collections = []
            for resource in resources:
                collections.extend(self._resolve_collection_targets(resource.bundle))
            return [c for c in collections if c]

        if isinstance(obj, CollectionObjectLanguage):
            collections = [
                info.collection for info in CollectionGeneralInfo.objects.filter(object_languages=obj)
            ]
            return [c for c in collections if c]

        if isinstance(obj, BundleObjectLanguage):
            collections = []
            for info in BundleGeneralInfo.objects.filter(object_languages=obj):
                collections.extend(self._resolve_collection_targets(info.bundle))
            return [c for c in collections if c]

        if isinstance(obj, CollectionRightsHolder):
            collections = [
                info.collection for info in CollectionAdministrativeInfo.objects.filter(rights_holders=obj)
            ]
            return [c for c in collections if c]

        if isinstance(obj, BundleRightsHolder):
            collections = []
            for info in BundleAdministrativeInfo.objects.filter(rights_holders=obj):
                collections.extend(self._resolve_collection_targets(info.bundle))
            return [c for c in collections if c]

        return []

    def _authorize(self, request, parent, publication_info=None) -> bool:
        if isinstance(parent, Bundle):
            return can_manage_bundle(request.user, parent)
        if isinstance(parent, Collection):
            return can_manage_collection(request.user, parent)

        targets = self._resolve_collection_targets(parent)
        if not targets and publication_info is not None and publication_info is not parent:
            targets = self._resolve_collection_targets(publication_info)

        return any(can_manage_collection(request.user, collection) for collection in targets)

    def get_parent(self, **kwargs):
        parent_id = kwargs.get(self.parent_kwarg)
        return get_object_or_404(self.parent_model, pk=parent_id)

    def get_publication_info(self, parent):
        if self.use_parent_as_info:
            return parent
        info = self.publication_model.objects.filter(**{self.publication_lookup: parent}).first()
        if info or not self.auto_create_info:
            return info
        info = self.publication_model(**{self.publication_lookup: parent})
        info.save()
        return info

    def get_related_object(self, publication_info, relation: str, object_id):
        qs = getattr(publication_info, relation).all()
        return get_object_or_404(qs, pk=object_id)

    def build_rows(self, parent, reference_slug: str, objects):
        rows = []
        for obj in objects:
            rows.append(
                {
                    "obj": obj,
                    "edit_url": reverse(
                        self.edit_url_name,
                        kwargs={
                            self.parent_kwarg: parent.pk,
                            "reference_slug": reference_slug,
                            "object_id": obj.pk,
                        },
                    ),
                    "remove_url": reverse(
                        self.remove_url_name,
                        kwargs={
                            self.parent_kwarg: parent.pk,
                            "reference_slug": reference_slug,
                            "object_id": obj.pk,
                        },
                    ),
                }
            )
        return rows

    def get_nested_panels(self, parent, reference_slug: str, edit_object):
        return []

    def prepare_object(self, obj, publication_info):
        return obj

    def render_panel(
        self,
        request,
        *,
        parent,
        reference_slug: str,
        publication_info,
        form=None,
        edit_object=None,
        message=None,
    ):
        config = self.get_reference_config(reference_slug)
        rows = []
        disabled_message = None
        if publication_info:
            objects = getattr(publication_info, config["relation"]).all()
            rows = self.build_rows(parent, reference_slug, objects)
        else:
            disabled_message = f"Save {self.info_label} before managing {config['item_label'].lower()}."

        panel_id = f"{self.panel_prefix}-{reference_slug}-panel"
        panel_url = reverse(
            self.panel_url_name,
            kwargs={self.parent_kwarg: parent.pk, "reference_slug": reference_slug},
        )
        form_action_url = panel_url
        if edit_object:
            form_action_url = reverse(
                self.edit_url_name,
                kwargs={
                    self.parent_kwarg: parent.pk,
                    "reference_slug": reference_slug,
                    "object_id": edit_object.pk,
                },
            )

        message_html = self.render_message_template(message) if message else None
        manage_url = config.get("manage_url")
        if manage_url is None:
            manage_url_name = config.get("manage_url_name")
            if manage_url_name:
                manage_kwargs = config.get("manage_url_kwargs", {})
                manage_url = reverse(manage_url_name, kwargs=manage_kwargs)

        nested_panels = []
        if edit_object:
            nested_panels = self.get_nested_panels(parent, reference_slug, edit_object)

        context = {
            "panel_id": panel_id,
            "panel_url": panel_url,
            "title": config["title"],
            "item_label": config["item_label"],
            "fields": config["fields"],
            "rows": rows,
            "form": form,
            "form_action_url": form_action_url,
            "edit_object": edit_object,
            "message_html": message_html,
            "disabled_message": disabled_message,
            "manage_url": manage_url,
            "nested_panels": nested_panels,
        }
        return render_to_string(self.template_name, context, request=request)

    def get(self, request, reference_slug: str, object_id=None, **kwargs):
        parent = self.get_parent(**kwargs)
        publication_info = self.get_publication_info(parent)
        if not self._authorize(request, parent, publication_info):
            raise PermissionDenied("Collection manager access required.")
        config = self.get_reference_config(reference_slug)
        edit_object = None
        form = None

        if publication_info:
            form = config["form"]()

        if object_id:
            if not publication_info:
                raise Http404("Publication info not found")
            edit_object = self.get_related_object(publication_info, config["relation"], object_id)
            form = config["form"](instance=edit_object)

        panel_html = self.render_panel(
            request,
            parent=parent,
            reference_slug=reference_slug,
            publication_info=publication_info,
            form=form,
            edit_object=edit_object,
        )
        return HttpResponse(panel_html)

    def post(self, request, reference_slug: str, object_id=None, **kwargs):
        parent = self.get_parent(**kwargs)
        publication_info = self.get_publication_info(parent)
        if not self._authorize(request, parent, publication_info):
            raise PermissionDenied("Collection manager access required.")
        config = self.get_reference_config(reference_slug)
        edit_object = None

        if not publication_info:
            panel_html = self.render_panel(
                request,
                parent=parent,
                reference_slug=reference_slug,
                publication_info=publication_info,
                form=None,
            )
            return HttpResponse(panel_html)

        if object_id:
            edit_object = self.get_related_object(publication_info, config["relation"], object_id)
            form = config["form"](request.POST, instance=edit_object)
        else:
            form = config["form"](request.POST)

        if form.is_valid():
            obj = form.save(commit=False)
            obj = self.prepare_object(obj, publication_info)
            apply_audit_fields(obj, request.user)
            obj.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()
            if not object_id:
                getattr(publication_info, config["relation"]).add(obj)
                message = f"{config['item_label']} added."
            else:
                message = f"{config['item_label']} updated."

            panel_html = self.render_panel(
                request,
                parent=parent,
                reference_slug=reference_slug,
                publication_info=publication_info,
                form=config["form"](),
                message=message,
            )
            return HttpResponse(panel_html)

        panel_html = self.render_panel(
            request,
            parent=parent,
            reference_slug=reference_slug,
            publication_info=publication_info,
            form=form,
            edit_object=edit_object,
        )
        return HttpResponse(panel_html)


class BasePublicationReferenceRemoveView(BasePublicationReferenceView):
    def remove_object(self, publication_info, relation: str, obj):
        getattr(publication_info, relation).remove(obj)

    def post(self, request, reference_slug: str, object_id=None, **kwargs):
        parent = self.get_parent(**kwargs)
        publication_info = self.get_publication_info(parent)
        config = self.get_reference_config(reference_slug)

        if not publication_info:
            panel_html = self.render_panel(
                request,
                parent=parent,
                reference_slug=reference_slug,
                publication_info=publication_info,
                form=None,
            )
            return HttpResponse(panel_html)

        obj = self.get_related_object(publication_info, config["relation"], object_id)
        self.remove_object(publication_info, config["relation"], obj)
        message = f"{config['item_label']} removed."

        panel_html = self.render_panel(
            request,
            parent=parent,
            reference_slug=reference_slug,
            publication_info=publication_info,
            form=config["form"](),
            message=message,
        )
        return HttpResponse(panel_html)


class CollectionPublicationReferencePanelView(BasePublicationReferenceView):
    reference_config = COLLECTION_PUBLICATION_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = CollectionPublicationInfo
    publication_lookup = "collection"
    parent_kwarg = "collection_id"
    panel_prefix = "collection"
    panel_url_name = "blam:collection_publication_reference_panel"
    edit_url_name = "blam:collection_publication_reference_edit"
    remove_url_name = "blam:collection_publication_reference_remove"


class CollectionPublicationReferenceEditView(CollectionPublicationReferencePanelView):
    pass


class CollectionPublicationReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = COLLECTION_PUBLICATION_REFERENCE_CONFIG
    parent_model = Collection
    publication_model = CollectionPublicationInfo
    publication_lookup = "collection"
    parent_kwarg = "collection_id"
    panel_prefix = "collection"
    panel_url_name = "blam:collection_publication_reference_panel"
    edit_url_name = "blam:collection_publication_reference_edit"
    remove_url_name = "blam:collection_publication_reference_remove"


class BundlePublicationReferencePanelView(BasePublicationReferenceView):
    reference_config = BUNDLE_PUBLICATION_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundlePublicationInfo
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle"
    panel_url_name = "blam:bundle_publication_reference_panel"
    edit_url_name = "blam:bundle_publication_reference_edit"
    remove_url_name = "blam:bundle_publication_reference_remove"


class BundlePublicationReferenceEditView(BundlePublicationReferencePanelView):
    pass


class BundlePublicationReferenceRemoveView(BasePublicationReferenceRemoveView):
    reference_config = BUNDLE_PUBLICATION_REFERENCE_CONFIG
    parent_model = Bundle
    publication_model = BundlePublicationInfo
    publication_lookup = "bundle"
    parent_kwarg = "bundle_id"
    panel_prefix = "bundle"
    panel_url_name = "blam:bundle_publication_reference_panel"
    edit_url_name = "blam:bundle_publication_reference_edit"
    remove_url_name = "blam:bundle_publication_reference_remove"
