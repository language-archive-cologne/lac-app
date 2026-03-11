from django.urls import include, path


app_name = "api"

urlpatterns = [
    path("", include("lacos.rest.urls")),
    path("v2/", include("lacos.rest.v2.urls")),
]
