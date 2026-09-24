import pymupdf as fitz
from django.test import TestCase

from pdf_editor.services import pdf_label_detector as det


def _make_pdf(lines, line_height=13, fontsize=10):
    doc = fitz.open()
    page = doc.new_page()
    y = 50
    for line in lines:
        if line is not None:
            page.insert_text((50, y), line, fontsize=fontsize, fontname='helv')
        y += line_height
    return doc


class LabelDetectorTests(TestCase):
    def test_detects_simple_colon_pair(self):
        doc = _make_pdf(['Invoice To: TMS PVT LTD'])
        candidates = det.detect_candidates(doc)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['label'], 'Invoice To')
        self.assertEqual(candidates[0]['value'], 'TMS PVT LTD')
        self.assertEqual(candidates[0]['separator'], ':')

    def test_detects_dash_separator(self):
        doc = _make_pdf(['Reference No. - INV-001'])
        candidates = det.detect_candidates(doc)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['separator'], '-')
        self.assertEqual(candidates[0]['value'], 'INV-001')

    def test_no_false_positive_without_any_separator(self):
        doc = _make_pdf(['Just a plain sentence with no separator'])
        candidates = det.detect_candidates(doc)
        self.assertEqual(candidates, [])

    def test_arbitrary_unseen_label_is_detected(self):
        """§10/§38: detection must not be limited to a hard-coded field list."""
        doc = _make_pdf(['Zorbnaxian Reference Code: XQ-999'])
        candidates = det.detect_candidates(doc)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['label'], 'Zorbnaxian Reference Code')
        self.assertEqual(candidates[0]['value'], 'XQ-999')

    def test_multiline_value_absorption(self):
        """§12/TEST 11: a bare label line absorbs following lines as one value."""
        doc = _make_pdf([
            'Address',
            '215-A, 2nd Floor, Chinar Incube Business Center,',
            'Hoshangabad Road, Bhopal, Madhya Pradesh, 462026',
        ])
        candidates = det.detect_candidates(doc)
        addr = next((c for c in candidates if c['label'] == 'Address'), None)
        self.assertIsNotNone(addr, f'no Address field found in {candidates}')
        self.assertIn('215-A', addr['value'])
        self.assertIn('Hoshangabad Road', addr['value'])
        self.assertIn('462026', addr['value'])

    def test_two_column_same_y_do_not_collide(self):
        """Two fields with the same label at the same y but different x (a
        common two-column supplier/recipient layout) must both be detected."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), 'Name : ABC LIMITED', fontsize=10, fontname='helv')
        page.insert_text((300, 100), 'Name : XYZ CORP', fontsize=10, fontname='helv')
        candidates = det.detect_candidates(doc)
        names = [c for c in candidates if c['label'] == 'Name']
        self.assertEqual(len(names), 2)
        values = {c['value'] for c in names}
        self.assertEqual(values, {'ABC LIMITED', 'XYZ CORP'})
