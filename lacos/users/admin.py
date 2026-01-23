from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.db import models
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import CollectionManagerAssignment, GroupACL, User

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


class AuthSourceFilter(admin.SimpleListFilter):
    title = _("Auth source")
    parameter_name = "auth_source"

    def lookups(self, request, model_admin):
        return (
            ("saml", _("SAML")),
            ("local", _("Local")),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "saml":
            return queryset.exclude(saml_persistent_id__isnull=True).exclude(
                saml_persistent_id="",
            )
        if value == "local":
            return queryset.filter(
                models.Q(saml_persistent_id__isnull=True)
                | models.Q(saml_persistent_id=""),
            )
        return queryset


class CollectionManagerAssignmentInline(admin.TabularInline):
    model = CollectionManagerAssignment
    fields = ("collection", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("collection",)
    extra = 0


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    readonly_fields = ("saml_persistent_id", "last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            _("Personal info"),
            {"fields": ("name", "email", "saml_persistent_id", "acl_agent_uri")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_display = [
        "username",
        "name",
        "email",
        "auth_source",
        "groups_list",
        "managed_collections",
        "last_login",
        "is_active",
        "is_staff",
        "is_superuser",
    ]
    search_fields = [
        "username",
        "name",
        "email",
        "saml_persistent_id",
        "acl_agent_uri",
    ]
    list_filter = [
        "is_active",
        "is_staff",
        "is_superuser",
        "groups",
        "last_login",
        "date_joined",
        AuthSourceFilter,
    ]
    ordering = ("username",)
    inlines = [CollectionManagerAssignmentInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("groups", "collection_manager_assignments__collection")

    @admin.display(description=_("Auth source"))
    def auth_source(self, obj):
        if obj.saml_persistent_id:
            return "SAML"
        return "Local"

    @admin.display(description=_("Groups"))
    def groups_list(self, obj):
        groups = [group.name for group in obj.groups.all()]
        return ", ".join(groups) if groups else "-"

    @admin.display(description=_("Managed collections"))
    def managed_collections(self, obj):
        identifiers = [
            assignment.collection.identifier
            for assignment in obj.collection_manager_assignments.all()
        ]
        if not identifiers:
            return "-"
        if len(identifiers) <= 3:
            return ", ".join(identifiers)
        remaining = len(identifiers) - 3
        return f"{', '.join(identifiers[:3])}, +{remaining}"


@admin.register(GroupACL)
class GroupACLAdmin(admin.ModelAdmin):
    list_display = ("group", "acl_agent_uri")
    search_fields = ("group__name", "acl_agent_uri")
    autocomplete_fields = ("group",)


@admin.register(CollectionManagerAssignment)
class CollectionManagerAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "collection", "created_at")
    search_fields = ("user__username", "user__email", "collection__identifier")
    autocomplete_fields = ("user", "collection")
