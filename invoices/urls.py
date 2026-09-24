from django.urls import path

from . import views

app_name = 'invoices'

urlpatterns = [
    # Upload / batch generation flow
    path('upload/', views.upload_view, name='upload'),
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/<int:pk>/preview/', views.batch_preview, name='batch_preview'),
    path('batches/<int:pk>/generate/', views.batch_generate, name='batch_generate'),
    path('batches/<int:pk>/', views.batch_detail, name='batch_detail'),
    path('batches/<int:pk>/delete/', views.batch_delete, name='batch_delete'),
    path('batches/<int:pk>/regenerate-failed/', views.batch_regenerate_failed, name='batch_regenerate_failed'),
    path('batches/<int:pk>/download-error-report/', views.batch_download_error_report, name='batch_download_error_report'),
    path('batches/<int:pk>/download-zip/', views.batch_download_zip, name='batch_download_zip'),
    path('batches/<int:pk>/download-all-pdf/', views.batch_download_all_pdf, name='batch_download_all_pdf'),
    path('batches/<int:pk>/download-all-docx/', views.batch_download_all_docx, name='batch_download_all_docx'),
    path('batches/<int:pk>/download-csv/', views.batch_download_csv, name='batch_download_csv'),

    # Invoice history / CRUD
    path('', views.invoice_list, name='invoice_list'),
    path('create/', views.invoice_create, name='invoice_create'),
    path('<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('<int:pk>/delete/', views.invoice_delete, name='invoice_delete'),
    path('<int:pk>/regenerate/', views.invoice_regenerate, name='invoice_regenerate'),
    path('<int:pk>/preview/', views.invoice_preview, name='invoice_preview'),
    path('<int:pk>/preview/raw/', views.invoice_preview_raw, name='invoice_preview_raw'),
    path('<int:pk>/download/pdf/', views.invoice_download_pdf, name='invoice_download_pdf'),
    path('<int:pk>/download/docx/', views.invoice_download_docx, name='invoice_download_docx'),

    # Bulk export
    path('bulk/download-zip/', views.bulk_download_zip, name='bulk_download_zip'),
    path('bulk/download-csv/', views.bulk_download_csv, name='bulk_download_csv'),
    path('bulk/delete/', views.bulk_delete, name='bulk_delete'),
]
