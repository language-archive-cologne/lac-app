from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.db import models
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import CollectionManagerAssignment, GroupACL, SamlCountry, SamlIdp, User

# ---------------------------------------------------------------------------
# SAML identification
# ---------------------------------------------------------------------------
# Going forward, the only SAML identifier accepted by the system is the user's
# eduPersonPrincipalName (EPPN), stored on ``User.acl_agent_uri`` with the
# prefix below. New SAML logins always populate this field; nothing should
# read or write ``saml_persistent_id`` for new accounts.
#
# ``saml_persistent_id`` predates the EPPN URI scheme. It is retained on the
# model only so that pre-migration accounts can still be back-classified as
# SAML in the admin (see ``is_legacy_saml``). Do not extend its use.
EPPN_ACL_AGENT_URI_PREFIX = "urn:lacos:eppn:"

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


# Q predicates shared between the helpers and the admin filter.
_EPPN_SAML_Q = models.Q(acl_agent_uri__startswith=EPPN_ACL_AGENT_URI_PREFIX)
_LEGACY_SAML_Q = models.Q(saml_persistent_id__isnull=False) & ~models.Q(
    saml_persistent_id="",
)


def is_eppn_saml(user: User) -> bool:
    """Return True iff ``user`` carries the canonical EPPN-based SAML URI."""
    return bool(
        user.acl_agent_uri
        and user.acl_agent_uri.startswith(EPPN_ACL_AGENT_URI_PREFIX),
    )


def is_legacy_saml(user: User) -> bool:
    """Return True iff ``user`` has a pre-migration ``saml_persistent_id``.

    Legacy-only path. New code must not rely on ``saml_persistent_id``.
    """
    return bool(user.saml_persistent_id)


def user_has_saml_identity(user: User) -> bool:
    """Return True iff ``user`` is SAML-authenticated, by either path."""
    return is_eppn_saml(user) or is_legacy_saml(user)


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
            return queryset.filter(_EPPN_SAML_Q | _LEGACY_SAML_Q)
        if value == "local":
            # Filter+exclude (rather than ``exclude(_EPPN_SAML_Q | _LEGACY_SAML_Q)``)
            # to stay NULL-safe across both nullable CharFields.
            return queryset.filter(
                models.Q(saml_persistent_id__isnull=True)
                | models.Q(saml_persistent_id=""),
            ).exclude(acl_agent_uri__startswith=EPPN_ACL_AGENT_URI_PREFIX)
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
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
    )
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

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("groups", "collection_manager_assignments__collection")

    @admin.display(description=_("Auth source"))
    def auth_source(self, obj):
        if user_has_saml_identity(obj):
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


@admin.register(SamlIdp)
class SamlIdpAdmin(admin.ModelAdmin):
    list_display = ("display_name", "country", "entity_id")
    search_fields = ("display_name", "entity_id")
    list_filter = ("country",)
    readonly_fields = ("entity_id", "display_name", "logo", "country")


@admin.register(SamlCountry)
class SamlCountryAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")
    readonly_fields = ("code", "name")
