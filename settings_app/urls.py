from django.urls import path

from . import views

app_name = 'settings_app'

urlpatterns = [
    path('company/', views.company_settings_view, name='company'),
    path('invoice/', views.invoice_settings_view, name='invoice'),
    path('signatures/', views.signatures_view, name='signatures'),
    path('signatures/<int:slot>/delete/', views.signature_delete, name='signature_delete'),
]
