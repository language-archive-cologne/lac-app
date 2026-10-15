from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View

from lacos.dbadmin.media_status import get_media_status_summary
from lacos.dbadmin.views import SuperuserRequiredMixin


class MediaStatusView(SuperuserRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        html = render_to_string(
            "dbadmin/partials/media_status.html",
            {"media": get_media_status_summary()},
            request=request,
        )
        return HttpResponse(html)
