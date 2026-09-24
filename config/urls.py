from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('accounts/', include('accounts.urls')),
    path('invoices/', include('invoices.urls')),
    path('pdf-editor/', include('pdf_editor.urls')),
    path('settings/', include('settings_app.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
