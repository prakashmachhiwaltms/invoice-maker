from django.conf import settings
from django.db import models
from django.urls import reverse


def original_pdf_path(instance, filename):
    return f'pdf_editor/originals/{filename}'


def version_pdf_path(instance, filename):
    return f'pdf_editor/versions/{instance.document_id}/{filename}'


class PdfBatch(models.Model):
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

    name = models.CharField(max_length=255, blank=True)
    total_files = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPLOADED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='pdf_batches')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['-created_at'])]

    def __str__(self):
        return self.name or f'PDF Batch #{self.pk}'

    def get_absolute_url(self):
        return reverse('pdf_editor:batch_detail', args=[self.pk])


class PdfDocument(models.Model):
    STATUS_UPLOADED = 'UPLOADED'
    STATUS_READY = 'READY'
    STATUS_SCANNED = 'SCANNED'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_UPLOADED, 'Uploaded'),
        (STATUS_READY, 'Ready'),
        (STATUS_SCANNED, 'Scanned / Image-based'),
        (STATUS_FAILED, 'Failed'),
    ]

    batch = models.ForeignKey(PdfBatch, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    original_file = models.FileField(upload_to=original_pdf_path)
    filename = models.CharField(max_length=255)
    current_version = models.ForeignKey(
        'PdfVersion', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    page_count = models.PositiveIntegerField(default=0)
    has_extractable_text = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPLOADED)
    error_message = models.CharField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='pdf_documents')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return self.filename

    def get_absolute_url(self):
        return reverse('pdf_editor:editor', args=[self.pk])

    @property
    def is_edited(self):
        return self.current_version_id is not None and self.current_version.version_number > 1

    @property
    def current_file(self):
        return self.current_version.file if self.current_version_id else self.original_file


class PdfVersion(models.Model):
    document = models.ForeignKey(PdfDocument, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    file = models.FileField(upload_to=version_pdf_path)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='pdf_versions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['document_id', 'version_number']
        unique_together = [('document', 'version_number')]
        indexes = [models.Index(fields=['document', 'version_number'])]

    def __str__(self):
        return f'{self.document.filename} v{self.version_number}'


class PdfField(models.Model):
    """A detected or manually-defined Label <separator> Value pair on a PDF.

    Rows are upserted by (document, page, label_key) whenever fields are
    (re)detected - see services/field_service.sync_detected_fields(). REJECTED
    and MANUAL rows are never touched by re-detection; DETECTED/CONFIRMED/EDITED
    rows have their value/bbox/confidence refreshed to track the live PDF.
    """
    CONFIDENCE_HIGH = 'HIGH'
    CONFIDENCE_MEDIUM = 'MEDIUM'
    CONFIDENCE_LOW = 'LOW'
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_HIGH, 'High confidence'),
        (CONFIDENCE_MEDIUM, 'Needs review'),
        (CONFIDENCE_LOW, 'Needs review'),
    ]

    STATUS_DETECTED = 'DETECTED'
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_MANUAL = 'MANUAL'
    STATUS_EDITED = 'EDITED'
    STATUS_CHOICES = [
        (STATUS_DETECTED, 'Detected'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_MANUAL, 'Manual'),
        (STATUS_EDITED, 'Edited'),
    ]

    document = models.ForeignKey(PdfDocument, on_delete=models.CASCADE, related_name='fields')
    page = models.PositiveIntegerField(default=0)

    label = models.CharField(max_length=255, blank=True)
    original_label = models.CharField(max_length=255, blank=True)
    label_key = models.CharField(max_length=255, blank=True, db_index=True)

    value = models.TextField(blank=True)
    original_value = models.TextField(blank=True)

    separator = models.CharField(max_length=10, blank=True, default=':')
    original_separator = models.CharField(max_length=10, blank=True, default=':')

    label_bbox = models.JSONField(default=dict, blank=True)
    value_bbox = models.JSONField(default=dict, blank=True)

    font = models.CharField(max_length=100, blank=True)
    font_size = models.FloatField(default=10)
    font_weight = models.CharField(max_length=10, blank=True, default='normal')
    color = models.JSONField(default=list, blank=True)

    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default=CONFIDENCE_MEDIUM)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DETECTED)
    is_detected = models.BooleanField(default=True)
    is_manual = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['page', 'label']
        indexes = [
            models.Index(fields=['document', 'page']),
            models.Index(fields=['document', 'label_key']),
        ]

    def __str__(self):
        return f'{self.label} ({self.document.filename} p{self.page})'

    @property
    def confidence_display(self):
        return 'High confidence' if self.confidence == self.CONFIDENCE_HIGH else 'Needs review'


class PdfEditOperation(models.Model):
    OP_REPLACE = 'REPLACE'
    OP_ADD = 'ADD'
    OP_DELETE = 'DELETE'
    OP_MOVE = 'MOVE'
    OP_LABEL_EDIT = 'LABEL_EDIT'
    OP_CHOICES = [
        (OP_REPLACE, 'Replace'),
        (OP_ADD, 'Add'),
        (OP_DELETE, 'Delete/Hide'),
        (OP_MOVE, 'Move'),
        (OP_LABEL_EDIT, 'Label/Value Edit'),
    ]

    document = models.ForeignKey(PdfDocument, on_delete=models.CASCADE, related_name='operations')
    version = models.ForeignKey(PdfVersion, on_delete=models.CASCADE, related_name='operations')
    operation_type = models.CharField(max_length=10, choices=OP_CHOICES)
    original_text = models.TextField(blank=True)
    replacement_text = models.TextField(blank=True)
    page = models.PositiveIntegerField(default=0)
    coordinates = models.JSONField(default=dict, blank=True)

    field = models.ForeignKey(PdfField, on_delete=models.SET_NULL, null=True, blank=True, related_name='operations')
    old_label = models.CharField(max_length=255, blank=True)
    new_label = models.CharField(max_length=255, blank=True)
    old_separator = models.CharField(max_length=10, blank=True)
    new_separator = models.CharField(max_length=10, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='pdf_edit_operations')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['document', '-created_at'])]

    def __str__(self):
        return f'{self.operation_type} on {self.document.filename} p{self.page}'


class PdfReplacementRuleSet(models.Model):
    """A saved, reusable set of multi-rule label/value replacements (§35).

    Deliberately not tied to a scope/batch/document selection - a saved set
    is just the rule logic, so it can be replayed against a different batch
    later. Scope is chosen fresh each time it's run.
    """
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='pdf_rule_sets')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class PdfReplacementRule(models.Model):
    MATCH_ANY = 'any'
    MATCH_EXACT = 'exact'
    MATCH_CONTAINS = 'contains'
    MATCH_STARTS_WITH = 'starts_with'
    MATCH_ENDS_WITH = 'ends_with'
    MATCH_NOT_EQUAL = 'not_equal'
    MATCH_REGEX = 'regex'
    MATCH_TYPE_CHOICES = [
        (MATCH_ANY, 'Any Value'),
        (MATCH_EXACT, 'Exact Match'),
        (MATCH_CONTAINS, 'Contains'),
        (MATCH_STARTS_WITH, 'Starts With'),
        (MATCH_ENDS_WITH, 'Ends With'),
        (MATCH_NOT_EQUAL, 'Does Not Equal'),
        (MATCH_REGEX, 'Regex (Advanced)'),
    ]

    rule_set = models.ForeignKey(PdfReplacementRuleSet, on_delete=models.CASCADE, related_name='rules')
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, default=MATCH_ANY)
    current_value = models.CharField(max_length=500, blank=True)
    case_sensitive = models.BooleanField(default=False)
    whitespace_normalize = models.BooleanField(default=True)
    change_label = models.BooleanField(default=False)
    new_label = models.CharField(max_length=255, blank=True)
    change_separator = models.BooleanField(default=False)
    new_separator = models.CharField(max_length=10, blank=True)
    new_value = models.CharField(max_length=500, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'Rule #{self.order} of {self.rule_set_id}'


class PdfReplacementRuleLabel(models.Model):
    rule = models.ForeignKey(PdfReplacementRule, on_delete=models.CASCADE, related_name='labels')
    label = models.CharField(max_length=255)

    def __str__(self):
        return self.label
