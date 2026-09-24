import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase

from invoices.models import Invoice
from invoices.services.invoice_generator import apply_tax_calculation, generate_invoice_files
from pdf_editor.models import PdfDocument, PdfVersion
from pdf_editor.services import document_service, label_rule_engine as engine


class ValueMatchesTests(TestCase):
    """Pure predicate tests - no DB/PDF needed (§3-§11)."""

    def test_any_always_matches(self):
        self.assertTrue(engine.value_matches('anything at all', 'any', ''))
        self.assertTrue(engine.value_matches('', 'any', 'ignored'))

    def test_exact_match(self):
        self.assertTrue(engine.value_matches('TMS PVT LTD', 'exact', 'TMS PVT LTD'))
        self.assertFalse(engine.value_matches('TMS PVT LTD EXTRA', 'exact', 'TMS PVT LTD'))

    def test_contains(self):
        self.assertTrue(engine.value_matches('ABC LTD', 'contains', 'LTD'))
        self.assertFalse(engine.value_matches('ABC CORP', 'contains', 'LTD'))

    def test_starts_with(self):
        self.assertTrue(engine.value_matches('TMS PVT LTD', 'starts_with', 'TMS'))
        self.assertFalse(engine.value_matches('THE TMS PVT LTD', 'starts_with', 'TMS'))

    def test_ends_with(self):
        self.assertTrue(engine.value_matches('ABC LTD', 'ends_with', 'LTD'))
        self.assertFalse(engine.value_matches('ABC LTD CO', 'ends_with', 'LTD'))

    def test_not_equal(self):
        self.assertTrue(engine.value_matches('XYZ PVT LTD', 'not_equal', 'Vellko Media'))
        self.assertFalse(engine.value_matches('Vellko Media', 'not_equal', 'Vellko Media'))

    def test_regex(self):
        self.assertTrue(engine.value_matches('INV-2024-001', 'regex', r'^INV-\d{4}-\d{3}$'))
        self.assertFalse(engine.value_matches('NOT-AN-INVOICE', 'regex', r'^INV-\d{4}-\d{3}$'))

    def test_bad_regex_is_no_match_not_an_error(self):
        self.assertFalse(engine.value_matches('anything', 'regex', '(unclosed['))

    def test_case_insensitive_by_default(self):
        self.assertTrue(engine.value_matches('tms pvt ltd', 'exact', 'TMS PVT LTD'))

    def test_case_sensitive_when_requested(self):
        self.assertFalse(engine.value_matches('tms pvt ltd', 'exact', 'TMS PVT LTD', case_sensitive=True))

    def test_whitespace_normalization(self):
        self.assertTrue(engine.value_matches('TMS   PVT LTD', 'exact', 'TMS PVT LTD'))

    def test_whitespace_normalization_disabled(self):
        self.assertFalse(engine.value_matches('TMS   PVT LTD', 'exact', 'TMS PVT LTD', whitespace_normalize=False))


class RuleParsingTests(TestCase):
    def test_rules_from_payload_matches_spec_shape(self):
        payload = [
            {'labels': ['Invoice To', 'Bill To'], 'match_type': 'any', 'new_value': 'Mahendra Pvt Ltd'},
            {'labels': ['Supplier'], 'match_type': 'exact', 'current_value': 'ABC LTD', 'new_value': 'Vellko Media'},
        ]
        rules = engine.rules_from_payload(payload)
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0].labels, ['Invoice To', 'Bill To'])
        self.assertEqual(rules[0].label_keys, {'invoice to', 'bill to'})
        self.assertEqual(rules[1].match_type, 'exact')

    def test_unknown_match_type_falls_back_to_any(self):
        rules = engine.rules_from_payload([{'labels': ['X'], 'match_type': 'bogus', 'new_value': 'Y'}])
        self.assertEqual(rules[0].match_type, 'any')


class RuleEngineIntegrationTests(TestCase):
    """§36 acceptance scenario: 3 PDFs, different labels, different values,
    different layouts - one multi-label rule per target field."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='ruletester', password='x')

    def _invoice_pdf_bytes(self, number, invoice_to_label_value, supplier_label_value):
        # invoice_to_label_value / supplier_label_value are (label_text, value) but
        # the generator only supports its own fixed labels ("Name :" for recipient,
        # supplier_name for supplier) - so to get *different* labels across PDFs
        # (Invoice To vs Bill To, Supplier vs Vendor) we post-process the rendered
        # PDF text via a manual field rename after generation, mirroring how a
        # real batch could contain differently-labelled invoices.
        inv = Invoice.objects.create(
            invoice_number=number, invoice_date=datetime.date(2024, 2, 4),
            invoice_to=invoice_to_label_value, supplier_name=supplier_label_value,
            supplier_address='1 Test Rd', description='Software Service', hsn='998314',
            quantity=Decimal('1'), total_value=Decimal('5000'), taxable_value=Decimal('5000'),
            tax_type='IGST', tax_rate=Decimal('18'),
        )
        apply_tax_calculation(inv)
        inv.save()
        generate_invoice_files(inv)
        inv.pdf_file.open('rb')
        data = inv.pdf_file.read()
        inv.pdf_file.close()
        return data

    def _make_document(self, filename, data):
        document = PdfDocument.objects.create(
            original_file=ContentFile(data, name=filename), filename=filename,
            uploaded_by=self.user, page_count=1, has_extractable_text=True, status=PdfDocument.STATUS_READY,
        )
        version = PdfVersion.objects.create(
            document=document, version_number=1, file=ContentFile(data, name=filename),
            note='Original upload', created_by=self.user,
        )
        document.current_version = version
        document.save(update_fields=['current_version'])
        return document

    def _relabel(self, document, old_label, old_value, new_label):
        """The generator's template literally prints "Name :" for both the
        supplier and recipient blocks, so both fields detect with the same
        label. Real invoices in the wild use distinct wording per §36
        ("Invoice To"/"Supplier" on some, "Bill To"/"Vendor" on others) - to
        exercise that without a second invoice template, rename each
        document's fields in place before the rule engine ever runs, so
        every document in this test genuinely has distinct, non-overlapping
        labels exactly matching the §36 scenario.
        """
        from pdf_editor.services import field_service
        field_service.sync_detected_fields(document)
        target = document.fields.get(label=old_label, value=old_value)
        field_service.apply_field_edit(document, self.user, target.pk, new_label, None, old_value)
        document.refresh_from_db()

    def setUp(self):
        data1 = self._invoice_pdf_bytes('RULETEST-001', 'TMS PVT LTD', 'ABC LTD')
        self.doc1 = self._make_document('RULETEST-001.pdf', data1)
        self._relabel(self.doc1, 'Name', 'TMS PVT LTD', 'Invoice To')
        self._relabel(self.doc1, 'Name', 'ABC LTD', 'Supplier')

        data2 = self._invoice_pdf_bytes('RULETEST-002', 'XYZ PVT LTD', 'DEF LTD')
        self.doc2 = self._make_document('RULETEST-002.pdf', data2)
        self._relabel(self.doc2, 'Name', 'XYZ PVT LTD', 'Invoice To')
        self._relabel(self.doc2, 'Name', 'DEF LTD', 'Supplier')

        data3 = self._invoice_pdf_bytes('RULETEST-003', 'SOME COMPANY', 'TEST LTD')
        self.doc3 = self._make_document('RULETEST-003.pdf', data3)
        self._relabel(self.doc3, 'Name', 'SOME COMPANY', 'Bill To')
        self._relabel(self.doc3, 'Name', 'TEST LTD', 'Vendor')

        self.originals = {
            d.pk: d.original_file.read() for d in (self.doc1, self.doc2, self.doc3)
        }
        for d in (self.doc1, self.doc2, self.doc3):
            d.original_file.seek(0)
        # setUp's own relabeling calls already created versions - capture the
        # baseline so tests can assert "+1 new version", not a hardcoded number.
        self.version_before = {d.pk: d.current_version.version_number for d in (self.doc1, self.doc2, self.doc3)}

    def test_multi_label_any_value_rule_normalizes_all_three_pdfs(self):
        rules = engine.rules_from_payload([
            {'labels': ['Invoice To', 'Bill To'], 'match_type': 'any', 'new_value': 'Mahendra Pvt Ltd'},
            {'labels': ['Supplier', 'Vendor'], 'match_type': 'any', 'new_value': 'Vellko Media'},
        ])
        # §36: doc1/doc2 use "Invoice To"/"Supplier", doc3 uses "Bill
        # To"/"Vendor" - one multi-label rule per target field must catch
        # every PDF regardless of which of its labels a given layout uses.
        documents = [self.doc1, self.doc2, self.doc3]

        preview = engine.build_preview(documents, rules)
        self.assertEqual(preview.affected_pdfs, 3)

        result = engine.apply_rules(documents, rules, self.user)
        self.assertEqual(result.affected, 3)
        self.assertEqual(result.skipped, 0)

        for d in (self.doc1, self.doc2, self.doc3):
            d.refresh_from_db()
            self.assertEqual(
                d.current_version.version_number, self.version_before[d.pk] + 1,
                f'{d.filename} should have exactly one new version from this apply',
            )
            text = document_service.open_fitz(d)[0].get_text('text')
            self.assertIn('Mahendra Pvt Ltd', text, f'{d.filename} missing new recipient value')
            self.assertIn('Vellko Media', text, f'{d.filename} missing new supplier value')
            # Original values must be gone.
            for old_value in ('TMS PVT LTD', 'XYZ PVT LTD', 'SOME COMPANY', 'ABC LTD', 'DEF LTD', 'TEST LTD'):
                self.assertNotIn(old_value, text)

        # Originals on disk are untouched (§7/§29/§30).
        for d in (self.doc1, self.doc2, self.doc3):
            d.original_file.open('rb')
            after = d.original_file.read()
            d.original_file.close()
            self.assertEqual(self.originals[d.pk], after)

    def test_exact_match_only_touches_matching_pdf(self):
        rules = engine.rules_from_payload([
            {'labels': ['Supplier'], 'match_type': 'exact', 'current_value': 'ABC LTD', 'new_value': 'Vellko Media'},
        ])
        documents = [self.doc1, self.doc2]  # doc1 supplier=ABC LTD, doc2 supplier=DEF LTD
        result = engine.apply_rules(documents, rules, self.user)
        self.assertEqual(result.affected, 1)
        self.assertEqual(result.skipped, 1)
        self.doc1.refresh_from_db()
        self.doc2.refresh_from_db()
        self.assertEqual(self.doc1.current_version.version_number, self.version_before[self.doc1.pk] + 1)
        self.assertEqual(self.doc2.current_version.version_number, self.version_before[self.doc2.pk])

    def test_skip_reason_when_label_not_found(self):
        rules = engine.rules_from_payload([
            {'labels': ['Nonexistent Label'], 'match_type': 'any', 'new_value': 'X'},
        ])
        preview = engine.build_preview([self.doc1], rules)
        self.assertEqual(preview.documents[0].status, 'skipped')
        self.assertIn('Nonexistent Label', preview.documents[0].skip_reason)

    def test_conflict_detection_and_priority_by_order(self):
        rules = engine.rules_from_payload([
            {'labels': ['Invoice To'], 'match_type': 'contains', 'current_value': 'TMS', 'new_value': 'Vellko'},
            {'labels': ['Invoice To'], 'match_type': 'any', 'new_value': 'Mahendra'},
        ])
        preview = engine.build_preview([self.doc1], rules)
        conflict_fields = [c for c in preview.conflicts if c['document'] == self.doc1]
        self.assertTrue(conflict_fields, 'expected at least one conflicting field on doc1')
        # Rule 0 (first in order) must win over rule 1 for the conflicting field.
        recipient_preview = next(
            fp for doc in preview.documents if doc.document == self.doc1
            for fp in doc.field_previews if fp['field'].value == 'TMS PVT LTD'
        )
        self.assertEqual(recipient_preview['rule_index'], 0)
        self.assertIn('Vellko', recipient_preview['after'])
