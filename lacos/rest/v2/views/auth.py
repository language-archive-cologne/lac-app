from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


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


@extend_schema(
    summary="Revoke refresh token",
    description="Blacklist a refresh token so it can no longer be used to mint access tokens.",
    tags=["auth"],
    request=None,
    responses={200: None, 400: None},
)
@api_view(["POST"])
@permission_classes([AllowAny])
def revoke_token(request):
    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return Response({"detail": "refresh is required"}, status=400)

    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
    except Exception:
        return Response({"detail": "invalid refresh token"}, status=400)

    return Response(status=200)
