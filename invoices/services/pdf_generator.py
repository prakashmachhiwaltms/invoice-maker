"""Server-side HTML -> PDF conversion for invoices, using xhtml2pdf.

xhtml2pdf is pure-Python (reportlab under the hood) so it needs no native
system libraries - unlike WeasyPrint, which requires the GTK/Pango/Cairo
runtime that is not readily available on a stock Windows machine. Output is
A4, print-ready, single page for normal-sized data.
"""
import os
from io import BytesIO

from django.conf import settings
from django.template.loader import render_to_string
from xhtml2pdf import pisa


_CSS_CACHE = None


def get_invoice_css() -> str:
    global _CSS_CACHE
    if _CSS_CACHE is None:
        css_path = os.path.join(settings.BASE_DIR, 'static', 'css', 'invoice.css')
        with open(css_path, 'r', encoding='utf-8') as fh:
            _CSS_CACHE = fh.read()
    return _CSS_CACHE


def _link_callback(uri, rel):
    """Resolve STATIC_URL/MEDIA_URL references to absolute filesystem paths
    so xhtml2pdf can embed images (logo, signatures) into the PDF."""
    if uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.BASE_DIR, 'static', uri.replace(settings.STATIC_URL, ''))
    elif uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ''))
    else:
        return uri
    return path


def render_invoice_html(context: dict, template_name='invoices/rcm_invoice.html') -> str:
    return render_to_string(template_name, context)


def build_invoice_pdf(context: dict, template_name='invoices/rcm_invoice.html') -> bytes:
    html = render_invoice_html(context, template_name)
    buffer = BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer, link_callback=_link_callback, encoding='utf-8')
    if result.err:
        raise RuntimeError('Failed to render invoice PDF (xhtml2pdf reported errors).')
    return buffer.getvalue()
