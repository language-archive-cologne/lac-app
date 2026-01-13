from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from lacos.blam.forms.metadata import (
    CollectionForm,
    CollectionHeaderForm,
    CollectionGeneralInfoForm,
    CollectionLocationForm,
    CollectionPublicationInfoForm,
    CollectionAdministrativeInfoForm,
    CollectionStructuralInfoForm,
    CollectionProjectInfoForm,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo
from lacos.blam.views.metadata.base import apply_audit_fields


def collection_nav_items(collection: Collection) -> list[dict]:
    return [
        {
            "slug": "overview",
            "label": "Overview",
            "url": reverse("blam:collection_metadata_overview", args=[collection.pk]),
        },
        {
            "slug": "header",
            "label": "Header",
            "url": reverse("blam:collection_metadata_header", args=[collection.pk]),
        },
        {
            "slug": "general",
            "label": "General",
            "url": reverse("blam:collection_metadata_general", args=[collection.pk]),
        },
        {
            "slug": "publication",
            "label": "Publication",
            "url": reverse("blam:collection_metadata_publication", args=[collection.pk]),
        },
        {
            "slug": "administrative",
            "label": "Administrative",
            "url": reverse("blam:collection_metadata_administrative", args=[collection.pk]),
        },
        {
            "slug": "structural",
            "label": "Structural",
            "url": reverse("blam:collection_metadata_structural", args=[collection.pk]),
        },
        {
            "slug": "projects",
            "label": "Projects",
            "url": reverse("blam:collection_metadata_projects", args=[collection.pk]),
        },
    ]


def render_collection_section(request, collection: Collection, section_slug: str, template_name: str, context: dict):
    base_context = {
        "collection": collection,
        "nav_items": collection_nav_items(collection),
        "active_section": section_slug,
    }
    base_context.update(context)
    return render(request, template_name, base_context)


class CollectionListView(View):
    def get(self, request):
        from django.db.models import Q

        search_query = request.GET.get("q", "").strip()
        collections = Collection.objects.all().order_by("identifier")

        if search_query:
            collections = collections.filter(
                Q(identifier__icontains=search_query) |
                Q(general_info__title__icontains=search_query) |
                Q(general_info__display_title__icontains=search_query)
            ).distinct()

        context = {"collections": collections, "search_query": search_query}

        if request.headers.get("HX-Request"):
            return render(request, "blam/metadata/partials/collection_table.html", context)

        return render(request, "blam/metadata/collection_list.html", context)


class CollectionCreateView(View):
    def get(self, request):
        form = CollectionForm()
        return render(request, "blam/metadata/collection_create.html", {"form": form})

    def post(self, request):
        form = CollectionForm(request.POST)
        if form.is_valid():
            collection = form.save(commit=False)
            apply_audit_fields(collection, request.user)
            collection.save()
            form.save_m2m()
            messages.success(request, "Collection created.")
            return redirect("blam:collection_metadata_overview", collection.pk)

        return render(request, "blam/metadata/collection_create.html", {"form": form})


class CollectionOverviewView(View):
    def get(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        form = CollectionForm(instance=collection)
        return render_collection_section(
            request,
            collection,
            "overview",
            "blam/metadata/collection_overview.html",
            {"form": form},
        )

    def post(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        form = CollectionForm(request.POST, instance=collection)
        if form.is_valid():
            collection = form.save(commit=False)
            apply_audit_fields(collection, request.user)
            collection.save()
            form.save_m2m()
            messages.success(request, "Collection updated.")
            return redirect("blam:collection_metadata_overview", collection.pk)

        return render_collection_section(
            request,
            collection,
            "overview",
            "blam/metadata/collection_overview.html",
            {"form": form},
        )


class CollectionHeaderView(View):
    def get(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionHeader.objects.filter(collection=collection).first()
        form = CollectionHeaderForm(instance=instance)
        return render_collection_section(
            request,
            collection,
            "header",
            "blam/metadata/collection_header.html",
            {"form": form},
        )

    def post(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionHeader.objects.filter(collection=collection).first()
        form = CollectionHeaderForm(request.POST, instance=instance)
        if form.is_valid():
            header = form.save(commit=False)
            header.collection = collection
            apply_audit_fields(header, request.user)
            header.save()
            form.save_m2m()
            messages.success(request, "Header updated.")
            return redirect("blam:collection_metadata_header", collection.pk)

        return render_collection_section(
            request,
            collection,
            "header",
            "blam/metadata/collection_header.html",
            {"form": form},
        )


class CollectionGeneralInfoView(View):
    def get(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionGeneralInfo.objects.filter(collection=collection).first()
        location_instance = instance.location if instance else None
        form = CollectionGeneralInfoForm(instance=instance)
        location_form = CollectionLocationForm(instance=location_instance, prefix="location")
        return render_collection_section(
            request,
            collection,
            "general",
            "blam/metadata/collection_general.html",
            {"form": form, "location_form": location_form},
        )

    def post(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionGeneralInfo.objects.filter(collection=collection).first()
        location_instance = instance.location if instance else None
        form = CollectionGeneralInfoForm(request.POST, instance=instance)
        location_form = CollectionLocationForm(
            request.POST, instance=location_instance, prefix="location"
        )

        if form.is_valid() and location_form.is_valid():
            location = location_form.save(commit=False)
            apply_audit_fields(location, request.user)
            location.save()
            general_info = form.save(commit=False)
            general_info.collection = collection
            general_info.location = location
            apply_audit_fields(general_info, request.user)
            general_info.save()
            form.save_m2m()
            messages.success(request, "General info updated.")
            return redirect("blam:collection_metadata_general", collection.pk)

        return render_collection_section(
            request,
            collection,
            "general",
            "blam/metadata/collection_general.html",
            {"form": form, "location_form": location_form},
        )


class CollectionPublicationInfoView(View):
    def get(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionPublicationInfo.objects.filter(collection=collection).first()
        form = CollectionPublicationInfoForm(instance=instance)
        return render_collection_section(
            request,
            collection,
            "publication",
            "blam/metadata/collection_publication.html",
            {"form": form},
        )

    def post(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionPublicationInfo.objects.filter(collection=collection).first()
        form = CollectionPublicationInfoForm(request.POST, instance=instance)
        if form.is_valid():
            publication_info = form.save(commit=False)
            publication_info.collection = collection
            apply_audit_fields(publication_info, request.user)
            publication_info.save()
            form.save_m2m()
            messages.success(request, "Publication info updated.")
            return redirect("blam:collection_metadata_publication", collection.pk)

        return render_collection_section(
            request,
            collection,
            "publication",
            "blam/metadata/collection_publication.html",
            {"form": form},
        )


class CollectionAdministrativeInfoView(View):
    def get(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionAdministrativeInfo.objects.filter(collection=collection).first()
        form = CollectionAdministrativeInfoForm(instance=instance)
        return render_collection_section(
            request,
            collection,
            "administrative",
            "blam/metadata/collection_administrative.html",
            {"form": form},
        )

    def post(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionAdministrativeInfo.objects.filter(collection=collection).first()
        form = CollectionAdministrativeInfoForm(request.POST, instance=instance)
        if form.is_valid():
            admin_info = form.save(commit=False)
            admin_info.collection = collection
            apply_audit_fields(admin_info, request.user)
            admin_info.save()
            form.save_m2m()
            messages.success(request, "Administrative info updated.")
            return redirect("blam:collection_metadata_administrative", collection.pk)

        return render_collection_section(
            request,
            collection,
            "administrative",
            "blam/metadata/collection_administrative.html",
            {"form": form},
        )


class CollectionStructuralInfoView(View):
    def get(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionStructuralInfo.objects.filter(collection=collection).first()
        form = CollectionStructuralInfoForm(instance=instance)
        return render_collection_section(
            request,
            collection,
            "structural",
            "blam/metadata/collection_structural.html",
            {"form": form},
        )

    def post(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        instance = CollectionStructuralInfo.objects.filter(collection=collection).first()
        form = CollectionStructuralInfoForm(request.POST, instance=instance)
        if form.is_valid():
            structural_info = form.save(commit=False)
            structural_info.collection = collection
            apply_audit_fields(structural_info, request.user)
            structural_info.save()
            form.save_m2m()
            messages.success(request, "Structural info updated.")
            return redirect("blam:collection_metadata_structural", collection.pk)

        return render_collection_section(
            request,
            collection,
            "structural",
            "blam/metadata/collection_structural.html",
            {"form": form},
        )


class CollectionProjectInfoView(View):
    def get(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        form = CollectionProjectInfoForm(instance=collection)
        return render_collection_section(
            request,
            collection,
            "projects",
            "blam/metadata/collection_projects.html",
            {"form": form},
        )

    def post(self, request, collection_id):
        collection = get_object_or_404(Collection, pk=collection_id)
        form = CollectionProjectInfoForm(request.POST, instance=collection)
        if form.is_valid():
            collection = form.save(commit=False)
            apply_audit_fields(collection, request.user)
            collection.save()
            form.save_m2m()
            messages.success(request, "Projects updated.")
            return redirect("blam:collection_metadata_projects", collection.pk)

        return render_collection_section(
            request,
            collection,
            "projects",
            "blam/metadata/collection_projects.html",
            {"form": form},
        )
