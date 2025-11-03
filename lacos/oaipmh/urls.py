from django.urls import path

from .views import oai_endpoint

app_name = "oaipmh"

urlpatterns = [
    path("", oai_endpoint, name="endpoint"),
]
