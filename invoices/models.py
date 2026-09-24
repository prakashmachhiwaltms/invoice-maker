from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse


def upload_path(instance, filename):
    return f'uploads/{filename}'


def error_report_path(instance, filename):
    return f'uploads/error_reports/{filename}'


class InvoiceBatch(models.Model):
    STATUS_UPLOADED = 'UPLOADED'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_UPLOADED, 'Uploaded'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    source_file = models.FileField(upload_to=upload_path)
    original_filename = models.CharField(max_length=255)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    generated_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPLOADED)
    error_report = models.FileField(upload_to=error_report_path, blank=True, null=True)
    error_summary = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='batches')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['-created_at'])]

    def __str__(self):
        return f'Batch #{self.pk} - {self.original_filename}'

    def get_absolute_url(self):
        return reverse('invoices:batch_detail', args=[self.pk])


class Invoice(models.Model):
    STATUS_GENERATED = 'GENERATED'
    STATUS_FAILED = 'FAILED'
    STATUS_PENDING = 'PENDING'
    STATUS_CHOICES = [
        (STATUS_GENERATED, 'Generated'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_PENDING, 'Pending'),
    ]

    TAX_TYPE_IGST = 'IGST'
    TAX_TYPE_CGST_SGST = 'CGST_SGST'
    TAX_TYPE_CHOICES = [
        (TAX_TYPE_IGST, 'IGST'),
        (TAX_TYPE_CGST_SGST, 'CGST + SGST'),
    ]

    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    invoice_date = models.DateField(db_index=True)
    invoice_to = models.CharField(max_length=255, blank=True, default='')

    supplier_name = models.CharField(max_length=255, db_index=True)
    supplier_address = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    state_code = models.CharField(max_length=10, blank=True)
    place_of_supply = models.CharField(max_length=100, blank=True)
    supplier_gstin = models.CharField(max_length=20, blank=True, default='NA')

    description = models.CharField(max_length=500)
    hsn = models.CharField('HSN/SAC', max_length=20, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1'))

    total_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    discount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    taxable_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))

    tax_type = models.CharField(max_length=10, choices=TAX_TYPE_CHOICES, default=TAX_TYPE_IGST)
    tax_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('18'))
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    cgst_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('0'))
    cgst_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    sgst_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('0'))
    sgst_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    igst_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('0'))
    igst_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))

    freight = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    insurance = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    packing = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))

    total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    amount_in_words = models.CharField(max_length=500, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.CharField(max_length=500, blank=True)

    batch = models.ForeignKey(InvoiceBatch, on_delete=models.CASCADE, null=True, blank=True, related_name='invoices')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='invoices')

    pdf_file = models.FileField(upload_to='generated/pdf/', blank=True, null=True)
    docx_file = models.FileField(upload_to='generated/docx/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['invoice_date']),
            models.Index(fields=['supplier_name']),
            models.Index(fields=['batch']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return self.invoice_number

    def get_absolute_url(self):
        return reverse('invoices:invoice_detail', args=[self.pk])

    @property
    def pdf_filename(self):
        from .services.utils import safe_filename
        return f'{safe_filename(self.invoice_number)}.pdf'

    @property
    def docx_filename(self):
        from .services.utils import safe_filename
        return f'{safe_filename(self.invoice_number)}.docx'
