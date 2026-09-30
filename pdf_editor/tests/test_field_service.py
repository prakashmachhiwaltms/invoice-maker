import datetime
from decimal import Decimal

import pymupdf as fitz
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

    def test_apply_field_edit_with_very_long_value_does_not_error(self):
        """Regression test for a live-reported 500: PdfVersion.note is a
        short CharField, but its text is built from the field's full
        label/value - a long absorbed multi-line value (e.g. a whole
        address block) could exceed the column's max_length and turn a
        normal edit into a raw "Data too long" database error instead of
        completing (with the note just truncated)."""
        doc = self._make_document()
        field_service.sync_detected_fields(doc)
        target = PdfField.objects.get(document=doc, label='Name', value='TMS PVT LTD')

        long_value = 'A very long replacement value ' * 15  # ~465 chars
        version = field_service.apply_field_edit(doc, self.user, target.pk, None, None, long_value)

        self.assertIsNotNone(version)
        self.assertLessEqual(len(version.note), 255)
        doc.refresh_from_db()
        self.assertEqual(doc.current_version.version_number, 2)

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

    def _make_two_column_document(self):
        """A two-column layout with a bare "Bill To" heading (right column,
        value on the line below - no printed separator) beside unrelated
        left-column text at similar Y positions, reproducing a live-reported
        bug."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), 'Anthropic, PBC', fontsize=10, fontname='helv')
        page.insert_text((50, 115), '548 Market Street', fontsize=10, fontname='helv')
        page.insert_text((300, 105), 'Bill To', fontsize=10, fontname='helv')
        page.insert_text((300, 120), 'Deepak Verma', fontsize=10, fontname='helv')
        data = doc.tobytes()
        document = PdfDocument.objects.create(
            original_file=ContentFile(data, name='TWOCOL-001.pdf'), filename='TWOCOL-001.pdf',
            uploaded_by=self.user, page_count=1, has_extractable_text=True, status=PdfDocument.STATUS_READY,
        )
        version = PdfVersion.objects.create(
            document=document, version_number=1, file=ContentFile(data, name='TWOCOL-001.pdf'),
            note='Original upload', created_by=self.user,
        )
        document.current_version = version
        document.save(update_fields=['current_version'])
        return document

    def test_stacked_bare_label_edit_keeps_label_and_value_on_separate_lines(self):
        """Regression test for a live-reported bug: editing the value of a
        bare-label field (label alone on one line, value absorbed from the
        line below - e.g. a "Bill To" heading) must not join them onto one
        line with a separator character that was never actually printed in
        the PDF. The edited PDF must keep the same two-line shape as the
        original.
        """
        doc = self._make_two_column_document()
        field_service.sync_detected_fields(doc)
        target = PdfField.objects.get(document=doc, label='Bill To', value='Deepak Verma')
        self.assertTrue(target.is_stacked)

        field_service.apply_field_edit(doc, self.user, target.pk, None, None, 'Vellko Media')
        doc.refresh_from_db()

        lines = document_service.open_fitz(doc)[0].get_text('text').splitlines()
        label_lines = [l for l in lines if l.strip() == 'Bill To']
        self.assertTrue(label_lines, f'no standalone "Bill To" line found in {lines!r}')
        self.assertNotIn('Bill To : Vellko Media', document_service.open_fitz(doc)[0].get_text('text'))
        self.assertNotIn('Bill To: Vellko Media', document_service.open_fitz(doc)[0].get_text('text'))
        value_lines = [l for l in lines if 'Vellko Media' in l]
        self.assertTrue(value_lines, f'no "Vellko Media" line found in {lines!r}')
        self.assertEqual(value_lines[0].strip(), 'Vellko Media')

        # The unrelated left-column text must be untouched.
        text = document_service.open_fitz(doc)[0].get_text('text')
        self.assertIn('Anthropic, PBC', text)
        self.assertIn('548 Market Street', text)

    def _make_bold_label_document(self):
        """A bold "Bill To" heading (narrow right column) with a multi-line
        address value below it, reproducing a live-reported bug: editing
        the value un-bolded the label and let the wrapped value spill far
        past its original column width."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((300, 100), 'Bill To', fontsize=10, fontname='hebo')
        page.insert_text((300, 115), 'Deepak Verma', fontsize=10, fontname='helv')
        page.insert_text((300, 130), 'Bhopal, MP', fontsize=10, fontname='helv')
        data = doc.tobytes()
        document = PdfDocument.objects.create(
            original_file=ContentFile(data, name='BOLDLABEL-001.pdf'), filename='BOLDLABEL-001.pdf',
            uploaded_by=self.user, page_count=1, has_extractable_text=True, status=PdfDocument.STATUS_READY,
        )
        version = PdfVersion.objects.create(
            document=document, version_number=1, file=ContentFile(data, name='BOLDLABEL-001.pdf'),
            note='Original upload', created_by=self.user,
        )
        document.current_version = version
        document.save(update_fields=['current_version'])
        return document

    def test_stacked_label_edit_keeps_bold_label_and_wraps_within_original_width(self):
        doc = self._make_bold_label_document()
        field_service.sync_detected_fields(doc)
        target = PdfField.objects.get(document=doc, label='Bill To')
        self.assertTrue(target.is_stacked)
        original_value_width = target.value_bbox['width']

        long_value = ('2nd floor, Phoenix Corporate Park, Narmadapuram Rd, '
                      'opposite Vrindavan garden, Bhopal, Madhya Pradesh 462026')
        field_service.apply_field_edit(doc, self.user, target.pk, None, None, long_value)
        doc.refresh_from_db()

        page_dict = document_service.open_fitz(doc)[0].get_text('dict')
        spans = [s for b in page_dict['blocks'] for l in b.get('lines', []) for s in l['spans']]

        label_spans = [s for s in spans if s['text'].strip() == 'Bill To']
        self.assertTrue(label_spans, 'no "Bill To" span found after edit')
        self.assertTrue(label_spans[0]['flags'] & (1 << 4), 'label lost its bold flag after the edit')

        value_spans = [s for s in spans if 'Phoenix Corporate Park' in s['text'] or 'Vrindavan' in s['text']
                       or 'Bhopal' in s['text'] or 'Madhya Pradesh' in s['text']]
        self.assertTrue(value_spans, 'no wrapped value text found after edit')
        # Every wrapped line must stay close to the ORIGINAL column's width,
        # not spill out toward the far side of the page (the bug let it
        # extend ~250pt+ further right, well past a reasonable margin).
        for s in value_spans:
            line_width = s['bbox'][2] - s['bbox'][0]
            self.assertLessEqual(
                line_width, original_value_width + 60,
                f'wrapped line "{s["text"]!r}" (width {line_width:.1f}) spilled past the original '
                f'column width ({original_value_width:.1f}) by more than a small margin',
            )

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
