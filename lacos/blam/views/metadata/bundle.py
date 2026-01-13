from django.contrib import messages
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from lacos.blam.forms.metadata import (
    BundleForm,
    BundleHeaderForm,
    BundleGeneralInfoForm,
    BundleLocationForm,
    BundlePublicationInfoForm,
    BundleAdministrativeInfoForm,
    BundleStructuralInfoForm,
    BundleResourcesForm,
    BundleProjectsForm,
    BundleMemberEntryForm,
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_header import BundleHeader
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleStructuralInfo,
    BundleMembers,
    BundleHasBundleMember,
    BundleResources,
)
from lacos.blam.views.metadata.base import apply_audit_fields


def bundle_nav_items(bundle: Bundle) -> list[dict]:
    return [
        {
            "slug": "overview",
            "label": "Overview",
            "url": reverse("blam:bundle_metadata_overview", args=[bundle.pk]),
        },
        {
            "slug": "header",
            "label": "Header",
            "url": reverse("blam:bundle_metadata_header", args=[bundle.pk]),
        },
        {
            "slug": "general",
            "label": "General",
            "url": reverse("blam:bundle_metadata_general", args=[bundle.pk]),
        },
        {
            "slug": "publication",
            "label": "Publication",
            "url": reverse("blam:bundle_metadata_publication", args=[bundle.pk]),
        },
        {
            "slug": "administrative",
            "label": "Administrative",
            "url": reverse("blam:bundle_metadata_administrative", args=[bundle.pk]),
        },
        {
            "slug": "structural",
            "label": "Structural",
            "url": reverse("blam:bundle_metadata_structural", args=[bundle.pk]),
        },
        {
            "slug": "members",
            "label": "Members",
            "url": reverse("blam:bundle_metadata_members", args=[bundle.pk]),
        },
        {
            "slug": "resources",
            "label": "Resources",
            "url": reverse("blam:bundle_metadata_resources", args=[bundle.pk]),
        },
        {
            "slug": "projects",
            "label": "Projects",
            "url": reverse("blam:bundle_metadata_projects", args=[bundle.pk]),
        },
    ]


def render_bundle_section(request, bundle: Bundle, section_slug: str, template_name: str, context: dict):
    base_context = {
        "bundle": bundle,
        "nav_items": bundle_nav_items(bundle),
        "active_section": section_slug,
    }
    base_context.update(context)
    return render(request, template_name, base_context)


class BundleListView(View):
    def get(self, request):
        from django.db.models import Q

        search_query = request.GET.get("q", "").strip()
        bundles = Bundle.objects.all().order_by("identifier")

        if search_query:
            bundles = bundles.filter(
                Q(identifier__icontains=search_query) |
                Q(general_info__title__icontains=search_query) |
                Q(general_info__display_title__icontains=search_query)
            ).distinct()

        context = {"bundles": bundles, "search_query": search_query}

        if request.headers.get("HX-Request"):
            return render(request, "blam/metadata/partials/bundle_table.html", context)

        return render(request, "blam/metadata/bundle_list.html", context)


class BundleCreateView(View):
    def get(self, request):
        form = BundleForm()
        return render(request, "blam/metadata/bundle_create.html", {"form": form})

    def post(self, request):
        form = BundleForm(request.POST)
        if form.is_valid():
            bundle = form.save(commit=False)
            apply_audit_fields(bundle, request.user)
            bundle.save()
            form.save_m2m()
            messages.success(request, "Bundle created.")
            return redirect("blam:bundle_metadata_overview", bundle.pk)

        return render(request, "blam/metadata/bundle_create.html", {"form": form})


class BundleOverviewView(View):
    def get(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        form = BundleForm(instance=bundle)
        return render_bundle_section(
            request,
            bundle,
            "overview",
            "blam/metadata/bundle_overview.html",
            {"form": form},
        )

    def post(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        form = BundleForm(request.POST, instance=bundle)
        if form.is_valid():
            bundle = form.save(commit=False)
            apply_audit_fields(bundle, request.user)
            bundle.save()
            form.save_m2m()
            messages.success(request, "Bundle updated.")
            return redirect("blam:bundle_metadata_overview", bundle.pk)

        return render_bundle_section(
            request,
            bundle,
            "overview",
            "blam/metadata/bundle_overview.html",
            {"form": form},
        )


class BundleHeaderView(View):
    def get(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleHeader.objects.filter(bundle=bundle).first()
        form = BundleHeaderForm(instance=instance)
        return render_bundle_section(
            request,
            bundle,
            "header",
            "blam/metadata/bundle_header.html",
            {"form": form},
        )

    def post(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleHeader.objects.filter(bundle=bundle).first()
        form = BundleHeaderForm(request.POST, instance=instance)
        if form.is_valid():
            header = form.save(commit=False)
            header.bundle = bundle
            apply_audit_fields(header, request.user)
            header.save()
            form.save_m2m()
            messages.success(request, "Header updated.")
            return redirect("blam:bundle_metadata_header", bundle.pk)

        return render_bundle_section(
            request,
            bundle,
            "header",
            "blam/metadata/bundle_header.html",
            {"form": form},
        )


class BundleGeneralInfoView(View):
    def get(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleGeneralInfo.objects.filter(bundle=bundle).first()
        location_instance = instance.location if instance else None
        form = BundleGeneralInfoForm(instance=instance)
        location_form = BundleLocationForm(instance=location_instance, prefix="location")
        return render_bundle_section(
            request,
            bundle,
            "general",
            "blam/metadata/bundle_general.html",
            {"form": form, "location_form": location_form},
        )

    def post(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleGeneralInfo.objects.filter(bundle=bundle).first()
        location_instance = instance.location if instance else None
        form = BundleGeneralInfoForm(request.POST, instance=instance)
        location_form = BundleLocationForm(
            request.POST, instance=location_instance, prefix="location"
        )

        if form.is_valid() and location_form.is_valid():
            location = location_form.save(commit=False)
            apply_audit_fields(location, request.user)
            location.save()
            general_info = form.save(commit=False)
            general_info.bundle = bundle
            general_info.location = location
            apply_audit_fields(general_info, request.user)
            general_info.save()
            form.save_m2m()
            messages.success(request, "General info updated.")
            return redirect("blam:bundle_metadata_general", bundle.pk)

        return render_bundle_section(
            request,
            bundle,
            "general",
            "blam/metadata/bundle_general.html",
            {"form": form, "location_form": location_form},
        )


class BundlePublicationInfoView(View):
    def get(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundlePublicationInfo.objects.filter(bundle=bundle).first()
        form = BundlePublicationInfoForm(instance=instance)
        return render_bundle_section(
            request,
            bundle,
            "publication",
            "blam/metadata/bundle_publication.html",
            {"form": form},
        )

    def post(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundlePublicationInfo.objects.filter(bundle=bundle).first()
        form = BundlePublicationInfoForm(request.POST, instance=instance)
        if form.is_valid():
            publication_info = form.save(commit=False)
            publication_info.bundle = bundle
            apply_audit_fields(publication_info, request.user)
            publication_info.save()
            form.save_m2m()
            messages.success(request, "Publication info updated.")
            return redirect("blam:bundle_metadata_publication", bundle.pk)

        return render_bundle_section(
            request,
            bundle,
            "publication",
            "blam/metadata/bundle_publication.html",
            {"form": form},
        )


class BundleAdministrativeInfoView(View):
    def get(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleAdministrativeInfo.objects.filter(bundle=bundle).first()
        form = BundleAdministrativeInfoForm(instance=instance)
        return render_bundle_section(
            request,
            bundle,
            "administrative",
            "blam/metadata/bundle_administrative.html",
            {"form": form},
        )

    def post(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleAdministrativeInfo.objects.filter(bundle=bundle).first()
        form = BundleAdministrativeInfoForm(request.POST, instance=instance)
        if form.is_valid():
            admin_info = form.save(commit=False)
            admin_info.bundle = bundle
            apply_audit_fields(admin_info, request.user)
            admin_info.save()
            form.save_m2m()
            messages.success(request, "Administrative info updated.")
            return redirect("blam:bundle_metadata_administrative", bundle.pk)

        return render_bundle_section(
            request,
            bundle,
            "administrative",
            "blam/metadata/bundle_administrative.html",
            {"form": form},
        )


class BundleStructuralInfoView(View):
    def get(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleStructuralInfo.objects.filter(bundle=bundle).first()
        form = BundleStructuralInfoForm(instance=instance)
        return render_bundle_section(
            request,
            bundle,
            "structural",
            "blam/metadata/bundle_structural.html",
            {"form": form},
        )

    def post(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleStructuralInfo.objects.filter(bundle=bundle).first()
        form = BundleStructuralInfoForm(request.POST, instance=instance)
        if form.is_valid():
            structural_info = form.save(commit=False)
            structural_info.bundle = bundle
            apply_audit_fields(structural_info, request.user)
            structural_info.save()
            form.save_m2m()
            messages.success(request, "Structural info updated.")
            return redirect("blam:bundle_metadata_structural", bundle.pk)

        return render_bundle_section(
            request,
            bundle,
            "structural",
            "blam/metadata/bundle_structural.html",
            {"form": form},
        )


class BundleMembersView(View):
    def get(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        bundle_members, created = BundleMembers.objects.get_or_create(bundle=bundle)
        if created:
            apply_audit_fields(bundle_members, request.user)
            bundle_members.save()
        formset_class = inlineformset_factory(
            BundleMembers,
            BundleHasBundleMember,
            form=BundleMemberEntryForm,
            extra=1,
            can_delete=True,
        )
        formset = formset_class(instance=bundle_members)
        return render_bundle_section(
            request,
            bundle,
            "members",
            "blam/metadata/bundle_members.html",
            {"formset": formset},
        )

    def post(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        bundle_members, created = BundleMembers.objects.get_or_create(bundle=bundle)
        if created:
            apply_audit_fields(bundle_members, request.user)
            bundle_members.save()
        formset_class = inlineformset_factory(
            BundleMembers,
            BundleHasBundleMember,
            form=BundleMemberEntryForm,
            extra=1,
            can_delete=True,
        )
        formset = formset_class(request.POST, instance=bundle_members)
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                apply_audit_fields(instance, request.user)
                instance.save()
            for deleted in formset.deleted_objects:
                deleted.delete()
            messages.success(request, "Bundle members updated.")
            return redirect("blam:bundle_metadata_members", bundle.pk)

        return render_bundle_section(
            request,
            bundle,
            "members",
            "blam/metadata/bundle_members.html",
            {"formset": formset},
        )


class BundleResourcesView(View):
    def get(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleResources.objects.filter(bundle=bundle).first()
        form = BundleResourcesForm(instance=instance)
        return render_bundle_section(
            request,
            bundle,
            "resources",
            "blam/metadata/bundle_resources.html",
            {"form": form},
        )

    def post(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        instance = BundleResources.objects.filter(bundle=bundle).first()
        form = BundleResourcesForm(request.POST, instance=instance)
        if form.is_valid():
            resources = form.save(commit=False)
            resources.bundle = bundle
            apply_audit_fields(resources, request.user)
            resources.save()
            form.save_m2m()
            messages.success(request, "Resources updated.")
            return redirect("blam:bundle_metadata_resources", bundle.pk)

        return render_bundle_section(
            request,
            bundle,
            "resources",
            "blam/metadata/bundle_resources.html",
            {"form": form},
        )


class BundleProjectsView(View):
    def get(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        form = BundleProjectsForm(instance=bundle)
        return render_bundle_section(
            request,
            bundle,
            "projects",
            "blam/metadata/bundle_projects.html",
            {"form": form},
        )

    def post(self, request, bundle_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        form = BundleProjectsForm(request.POST, instance=bundle)
        if form.is_valid():
            bundle = form.save(commit=False)
            apply_audit_fields(bundle, request.user)
            bundle.save()
            form.save_m2m()
            messages.success(request, "Projects updated.")
            return redirect("blam:bundle_metadata_projects", bundle.pk)

        return render_bundle_section(
            request,
            bundle,
            "projects",
            "blam/metadata/bundle_projects.html",
            {"form": form},
        )
