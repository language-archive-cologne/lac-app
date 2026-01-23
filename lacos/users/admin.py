from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import CollectionManagerAssignment, GroupACL, User

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    readonly_fields = ("saml_persistent_id",)
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
        "saml_persistent_id",
        "acl_agent_uri",
        "is_superuser",
    ]
    search_fields = [
        "username",
        "name",
        "email",
        "saml_persistent_id",
        "acl_agent_uri",
    ]


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
