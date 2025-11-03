from rest_framework import serializers

from lacos.users.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["username", "name", "saml_persistent_id", "url"]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "username"},
            "saml_persistent_id": {"read_only": True},
        }
