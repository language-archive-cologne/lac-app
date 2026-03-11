from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="Validate JWT token",
    description="Validates the Bearer token in the Authorization header and returns the authenticated user info.",
    tags=["auth"],
    responses={200: None, 401: None},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def validate_token(request):
    """Validate a Bearer token and return user info."""
    return Response({
        "username": request.user.username,
        "is_active": request.user.is_active,
    })
