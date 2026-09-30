from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

from django.http import FileResponse, HttpResponse
from pathlib import Path

def favicon_view(request):
    favicon_file = Path(settings.BASE_DIR) / 'static' / 'img' / 'favicon.ico'
    if favicon_file.exists():
        return FileResponse(open(favicon_file, 'rb'), content_type='image/x-icon')
    return HttpResponse(status=204)

urlpatterns = [
    path('favicon.ico', favicon_view),
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('accounts/', include('accounts.urls')),
    path('invoices/', include('invoices.urls')),
    path('pdf-editor/', include('pdf_editor.urls')),
    path('settings/', include('settings_app.urls')),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

