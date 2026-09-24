import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase

from invoices.models import Invoice
from invoices.services.invoice_generator import apply_tax_calculation, generate_invoice_files
from pdf_editor.models import PdfDocument, PdfField, PdfVersion
from pdf_editor.services import document_service, field_service


class FieldServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='fieldtester', password='x')
        inv = Invoice.objects.create(
            invoice_number='FIELDTEST-001', invoice_date=datetime.date(2024, 2, 4), invoice_to='TMS PVT LTD',
            supplier_name='ABC LIMITED', supplier_address='1 Test Rd', description='Software Service',
            hsn='998314', quantity=Decimal('1'), total_value=Decimal('5000'), taxable_value=Decimal('5000'),
            tax_type='IGST', tax_rate=Decimal('18'),
        )
        apply_tax_calculation(inv)
        inv.save()
        generate_invoice_files(inv)
        cls.invoice = inv

    def _make_document(self):
        self.invoice.pdf_file.open('rb')
        data = self.invoice.pdf_file.read()
        self.invoice.pdf_file.close()
        document = PdfDocument.objects.create(
            original_file=ContentFile(data, name='FIELDTEST-001.pdf'), filename='FIELDTEST-001.pdf',
            uploaded_by=self.user, page_count=1, has_extractable_text=True, status=PdfDocument.STATUS_READY,
        )
        version = PdfVersion.objects.create(
            document=document, version_number=1, file=ContentFile(data, name='FIELDTEST-001.pdf'),
            note='Original upload', created_by=self.user,
        )
        document.current_version = version
        document.save(update_fields=['current_version'])
        return document

    def test_sync_detects_fields_without_duplicates(self):
        doc = self._make_document()
        fields = field_service.sync_detected_fields(doc)
        self.assertGreater(fields.count(), 5)
        # Re-running sync must not create duplicates.
        count_before = doc.fields.count()
        field_service.sync_detected_fields(doc)
        self.assertEqual(doc.fields.count(), count_before)

    def test_apply_field_edit_changes_label_separator_and_value(self):
        doc = self._make_document()
        field_service.sync_detected_fields(doc)
        target = PdfField.objects.get(document=doc, label='Name', value='TMS PVT LTD')

        field_service.apply_field_edit(doc, self.user, target.pk, 'Customer', '-', 'MAHENDRA PVT LTD')
        doc.refresh_from_db()

        self.assertEqual(doc.current_version.version_number, 2)
        text = document_service.open_fitz(doc)[0].get_text('text')
        self.assertIn('Customer - MAHENDRA PVT LTD', text)
        self.assertNotIn('TMS PVT LTD', text)

        target.refresh_from_db()
        self.assertEqual(target.status, PdfField.STATUS_EDITED)
        self.assertEqual(target.original_label, 'Name')
        self.assertEqual(target.original_value, 'TMS PVT LTD')

    def test_original_file_untouched_after_edit(self):
        doc = self._make_document()
        original_bytes = doc.original_file.read()
        doc.original_file.seek(0)
        field_service.sync_detected_fields(doc)
        target = PdfField.objects.get(document=doc, label='Name', value='TMS PVT LTD')
        field_service.apply_field_edit(doc, self.user, target.pk, None, None, 'CHANGED VALUE')
        doc.refresh_from_db()
        doc.original_file.open('rb')
        after_bytes = doc.original_file.read()
        doc.original_file.close()
        self.assertEqual(original_bytes, after_bytes)

    def test_undo_redo_resyncs_field_state(self):
        doc = self._make_document()
        field_service.sync_detected_fields(doc)
        target = PdfField.objects.get(document=doc, label='Name', value='TMS PVT LTD')
        field_id = target.pk

        field_service.apply_field_edit(doc, self.user, field_id, 'Customer', '-', 'MAHENDRA PVT LTD')
        doc.refresh_from_db()

        self.assertTrue(document_service.undo(doc))
        doc.refresh_from_db()
        self.assertEqual(doc.current_version.version_number, 1)
        reverted = PdfField.objects.get(pk=field_id)
        self.assertEqual(reverted.label, 'Name')
        self.assertEqual(reverted.value, 'TMS PVT LTD')
        # No duplicate row should have been created by the resync.
        self.assertEqual(PdfField.objects.filter(document=doc, label='Name', value='TMS PVT LTD').count(), 1)

        self.assertTrue(document_service.redo(doc))
        doc.refresh_from_db()
        self.assertEqual(doc.current_version.version_number, 2)
        reapplied = PdfField.objects.get(pk=field_id)
        self.assertEqual(reapplied.label, 'Customer')
        self.assertEqual(reapplied.value, 'MAHENDRA PVT LTD')

    def test_manual_field_creation_and_reject_survive_resync(self):
        doc = self._make_document()
        field_service.sync_detected_fields(doc)
        fitz_doc = document_service.open_fitz(doc)
        from pdf_editor.services import extraction
        spans = extraction.get_page_text_blocks(fitz_doc, 0)
        span = next(s for s in spans if 'Software Service' in s['text'])

        manual = field_service.create_manual_field(doc, self.user, 0, span['id'], 'Custom Label', 'Custom Value', ':')
        self.assertEqual(manual.status, PdfField.STATUS_MANUAL)

        some_detected = doc.fields.filter(status=PdfField.STATUS_DETECTED).first()
        field_service.reject_field(some_detected)

        field_service.sync_detected_fields(doc)
        manual.refresh_from_db()
        some_detected.refresh_from_db()
        self.assertEqual(manual.status, PdfField.STATUS_MANUAL)
        self.assertEqual(manual.label, 'Custom Label')
        self.assertEqual(some_detected.status, PdfField.STATUS_REJECTED)
