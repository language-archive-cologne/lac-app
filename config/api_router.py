from django.conf import settings
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from lacos.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)


app_name = "api"
urlpatterns = router.urls

# Include REST app URLs
urlpatterns += [
    path("", include("lacos.rest.urls")),
    path("v2/", include("lacos.rest.v2.urls")),
]
