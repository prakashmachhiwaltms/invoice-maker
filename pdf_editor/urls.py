from django.urls import path

from . import views

app_name = 'pdf_editor'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('upload/', views.upload_view, name='upload'),
    path('library/', views.library_view, name='library'),

    path('batches/', views.batch_list, name='batch_list'),
    path('batches/<int:pk>/', views.batch_detail, name='batch_detail'),
    path('batches/<int:pk>/delete/', views.batch_delete, name='batch_delete'),
    path('batches/<int:pk>/download-zip/', views.batch_download_zip, name='batch_download_zip'),

    path('find-replace/', views.find_replace_view, name='find_replace'),
    path('find-replace/apply/', views.find_replace_apply, name='find_replace_apply'),

    path('label-editor/', views.label_editor_home, name='label_editor_home'),
    path('label-editor/preview/', views.label_editor_preview, name='label_editor_preview'),
    path('label-editor/apply/', views.label_editor_apply, name='label_editor_apply'),
    path('label-editor/discover/', views.label_editor_discover, name='label_editor_discover'),
    path('label-editor/rule-sets/', views.label_rule_sets, name='label_rule_sets'),
    path('label-editor/rule-sets/<int:pk>/', views.label_rule_set_detail, name='label_rule_set_detail'),

    path('document/<int:pk>/edit/', views.editor_view, name='editor'),
    path('document/<int:pk>/label-editor/', views.label_editor_view, name='label_editor'),
    path('document/<int:pk>/versions/', views.document_versions_view, name='document_versions'),
    path('document/<int:pk>/download/', views.download_current, name='download_current'),
    path('document/<int:pk>/versions/<int:version_number>/download/', views.download_version, name='download_version'),
    path('document/<int:pk>/duplicate/', views.duplicate_document, name='duplicate'),
    path('document/<int:pk>/delete/', views.delete_document, name='delete'),

    path('document/<int:pk>/api/page/<int:page_number>/', views.api_page_data, name='api_page_data'),
    path('document/<int:pk>/api/page/<int:page_number>/image/', views.api_page_image, name='api_page_image'),
    path('document/<int:pk>/api/replace/', views.api_replace, name='api_replace'),
    path('document/<int:pk>/api/add-text/', views.api_add_text, name='api_add_text'),
    path('document/<int:pk>/api/hide/', views.api_hide, name='api_hide'),
    path('document/<int:pk>/api/move/', views.api_move, name='api_move'),
    path('document/<int:pk>/api/undo/', views.api_undo, name='api_undo'),
    path('document/<int:pk>/api/redo/', views.api_redo, name='api_redo'),
    path('document/<int:pk>/api/search/', views.api_search, name='api_search'),
    path('document/<int:pk>/api/replace-all/', views.api_replace_all, name='api_replace_all'),

    path('document/<int:pk>/api/fields/', views.api_fields_list, name='api_fields_list'),
    path('document/<int:pk>/api/fields/redetect/', views.api_fields_redetect, name='api_fields_redetect'),
    path('document/<int:pk>/api/fields/manual/', views.api_field_manual_create, name='api_field_manual_create'),
    path('document/<int:pk>/api/fields/<int:field_id>/apply/', views.api_field_apply, name='api_field_apply'),
    path('document/<int:pk>/api/fields/<int:field_id>/confirm/', views.api_field_confirm, name='api_field_confirm'),
    path('document/<int:pk>/api/fields/<int:field_id>/reject/', views.api_field_reject, name='api_field_reject'),
]
