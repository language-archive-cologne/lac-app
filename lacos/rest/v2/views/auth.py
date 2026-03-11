from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken


@extend_schema(
    summary="Exchange session for JWT",
    description=(
        "Issues a JWT access/refresh token pair for the currently authenticated session. "
        "Use this after Shibboleth login to obtain tokens for API access."
    ),
    tags=["auth"],
    responses={200: None, 401: None},
)
@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def session_token(request):
    """Exchange an active session (e.g. Shibboleth) for a JWT token pair."""
    refresh = RefreshToken.for_user(request.user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    })


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
