from django.contrib import admin

from .models import Invoice, InvoiceBatch


@admin.register(InvoiceBatch)
class InvoiceBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_filename', 'total_rows', 'valid_rows', 'invalid_rows',
                     'generated_count', 'failed_count', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('original_filename',)
    ordering = ('-created_at',)
    readonly_fields = ('total_rows', 'valid_rows', 'invalid_rows', 'generated_count', 'failed_count', 'created_at')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'invoice_date', 'supplier_name', 'taxable_value',
                     'tax_amount', 'total', 'status', 'batch', 'created_by', 'created_at')
    list_filter = ('status', 'tax_type', 'invoice_date', 'created_at')
    search_fields = ('invoice_number', 'supplier_name', 'description')
    ordering = ('-created_at',)
    date_hierarchy = 'invoice_date'
    readonly_fields = ('created_at', 'updated_at', 'amount_in_words')
    fieldsets = (
        ('Invoice', {'fields': ('invoice_number', 'invoice_date', 'invoice_to', 'status', 'error_message', 'batch', 'created_by')}),
        ('Supplier', {'fields': ('supplier_name', 'supplier_address', 'country', 'state', 'state_code', 'place_of_supply', 'supplier_gstin')}),
        ('Line item', {'fields': ('description', 'hsn', 'quantity', 'total_value', 'discount', 'taxable_value')}),
        ('Tax', {'fields': ('tax_type', 'tax_rate', 'tax_amount', 'cgst_rate', 'cgst_amount', 'sgst_rate', 'sgst_amount', 'igst_rate', 'igst_amount')}),
        ('Other charges', {'fields': ('freight', 'insurance', 'packing', 'total', 'amount_in_words')}),
        ('Files', {'fields': ('pdf_file', 'docx_file')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )
