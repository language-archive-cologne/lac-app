from django.urls import include, path


app_name = "api"

urlpatterns = [
    path("v2/", include("lacos.rest.v2.urls")),
]
