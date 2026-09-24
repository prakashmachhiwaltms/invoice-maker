from django.contrib import admin

from .models import PdfBatch, PdfDocument, PdfEditOperation, PdfVersion


@admin.register(PdfBatch)
class PdfBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'total_files', 'processed_count', 'failed_count', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('name',)
    ordering = ('-created_at',)


@admin.register(PdfDocument)
class PdfDocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'filename', 'batch', 'page_count', 'has_extractable_text', 'status', 'uploaded_by', 'created_at')
    list_filter = ('status', 'has_extractable_text', 'created_at')
    search_fields = ('filename',)
    ordering = ('-created_at',)


@admin.register(PdfVersion)
class PdfVersionAdmin(admin.ModelAdmin):
    list_display = ('id', 'document', 'version_number', 'note', 'created_by', 'created_at')
    list_filter = ('created_at',)
    ordering = ('document', 'version_number')


@admin.register(PdfEditOperation)
class PdfEditOperationAdmin(admin.ModelAdmin):
    list_display = ('id', 'document', 'operation_type', 'page', 'created_by', 'created_at')
    list_filter = ('operation_type', 'created_at')
    ordering = ('-created_at',)
