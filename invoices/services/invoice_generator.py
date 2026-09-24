"""Orchestrates turning one validated spreadsheet row (or manual form data)
into a fully generated Invoice: tax calculation, amount-in-words, and the
PDF/DOCX files. Every valid row produces exactly one invoice - rows are never
merged or grouped by supplier.
"""
import logging
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction

from settings_app.models import CompanySettings, InvoiceSettings, Signature

from .amount_to_words import amount_to_words
from .docx_generator import build_invoice_docx
from .pdf_generator import build_invoice_pdf, get_invoice_css
from .tax_calculator import calculate_tax
from .utils import safe_filename

logger = logging.getLogger('invoices')


def next_invoice_number(prefix=None, padding=None):
    from invoices.models import Invoice

    settings_obj = InvoiceSettings.get_solo()
    prefix = prefix if prefix is not None else settings_obj.invoice_number_prefix
    padding = padding if padding is not None else settings_obj.invoice_number_padding

    existing = Invoice.objects.filter(invoice_number__startswith=prefix).count()
    seq = settings_obj.invoice_number_start + existing
    while True:
        candidate = f'{prefix}{str(seq).zfill(padding)}'
        if not Invoice.objects.filter(invoice_number=candidate).exists():
            return candidate
        seq += 1


def get_invoice_context(invoice):
    company = CompanySettings.get_solo()
    invoice_settings = InvoiceSettings.get_solo()
    sig1 = Signature.objects.filter(slot=1, is_active=True).first()
    sig2 = Signature.objects.filter(slot=2, is_active=True).first()

    return {
        'invoice': invoice,
        'invoice_title': invoice_settings.invoice_title,
        'company_name': company.company_name,
        'company_address': company.company_address,
        'company_gstin': company.gstin,
        'company_state': company.state,
        'company_state_code': company.state_code,
        'invoice_number': invoice.invoice_number,
        'invoice_date': invoice.invoice_date,
        'invoice_to': invoice.invoice_to or invoice_settings.invoice_to,
        'supplier_name': invoice.supplier_name,
        'supplier_address': invoice.supplier_address,
        'country': invoice.country,
        'state': invoice.state,
        'state_code': invoice.state_code,
        'place_of_supply': invoice.place_of_supply or company.place_of_supply,
        'supplier_gstin': invoice.supplier_gstin or 'NA',
        'description': invoice.description,
        'hsn': invoice.hsn,
        'quantity': invoice.quantity,
        'total_value': invoice.total_value,
        'discount': invoice.discount,
        'taxable_value': invoice.taxable_value,
        'tax_type': invoice.tax_type,
        'tax_rate': invoice.tax_rate,
        'tax_amount': invoice.tax_amount,
        'cgst_rate': invoice.cgst_rate,
        'cgst_amount': invoice.cgst_amount,
        'sgst_rate': invoice.sgst_rate,
        'sgst_amount': invoice.sgst_amount,
        'igst_rate': invoice.igst_rate,
        'igst_amount': invoice.igst_amount,
        'freight': invoice.freight,
        'insurance': invoice.insurance,
        'packing': invoice.packing,
        'total': invoice.total,
        'amount_in_words': invoice.amount_in_words,
        'footer_text': invoice_settings.footer_for_text,
        'reverse_charge_note': invoice_settings.reverse_charge_note,
        'authorized_signatory_text': invoice_settings.authorized_signatory_text,
        'currency_symbol': invoice_settings.currency_symbol,
        'signature1': sig1,
        'signature2': sig2,
        'company_logo_url': company.logo.url if company.logo else None,
        'blank_rows': range(3),
        'inline_css': get_invoice_css(),
    }


def apply_tax_calculation(invoice, precision=None):
    invoice_settings = InvoiceSettings.get_solo()
    precision = precision if precision is not None else invoice_settings.rounding_precision

    breakdown = calculate_tax(
        taxable_value=invoice.taxable_value,
        tax_rate=invoice.tax_rate,
        tax_amount=invoice.tax_amount,
        tax_type=invoice.tax_type,
        freight=invoice.freight,
        insurance=invoice.insurance,
        packing=invoice.packing,
        precision=precision,
    )
    invoice.taxable_value = breakdown.taxable_value
    invoice.tax_rate = breakdown.tax_rate
    invoice.tax_amount = breakdown.tax_amount
    invoice.cgst_rate = breakdown.cgst_rate
    invoice.cgst_amount = breakdown.cgst_amount
    invoice.sgst_rate = breakdown.sgst_rate
    invoice.sgst_amount = breakdown.sgst_amount
    invoice.igst_rate = breakdown.igst_rate
    invoice.igst_amount = breakdown.igst_amount
    invoice.freight = breakdown.freight
    invoice.insurance = breakdown.insurance
    invoice.packing = breakdown.packing
    if not invoice.total_value:
        invoice.total_value = invoice.taxable_value
    invoice.total = breakdown.total

    invoice.amount_in_words = amount_to_words(invoice.total, fmt=invoice_settings.amount_words_format)
    return invoice


@transaction.atomic
def create_invoice_from_row(data: dict, batch=None, user=None):
    from invoices.models import Invoice

    invoice_settings = InvoiceSettings.get_solo()
    invoice_number = data.get('invoice_number') or next_invoice_number()

    invoice = Invoice(
        invoice_number=invoice_number,
        invoice_date=data['invoice_date'],
        invoice_to=data.get('invoice_to') or '',
        supplier_name=data['supplier_name'],
        supplier_address=data['supplier_address'],
        country=data.get('country', ''),
        state=data.get('state', ''),
        state_code=data.get('state_code', ''),
        place_of_supply=data.get('place_of_supply', ''),
        supplier_gstin=data.get('supplier_gstin') or 'NA',
        description=data['description'],
        hsn=data.get('hsn') or invoice_settings.default_hsn,
        quantity=data.get('quantity') or Decimal('1'),
        total_value=data.get('taxable_value') or Decimal('0'),
        discount=data.get('discount') or Decimal('0'),
        taxable_value=data.get('taxable_value') or Decimal('0'),
        tax_rate=data.get('tax_rate') if data.get('tax_rate') is not None else invoice_settings.default_tax_rate,
        tax_amount=data.get('tax_amount'),
        freight=data.get('freight') or Decimal('0'),
        insurance=data.get('insurance') or Decimal('0'),
        packing=data.get('packing') or Decimal('0'),
        batch=batch,
        created_by=user,
        status=Invoice.STATUS_PENDING,
    )
    apply_tax_calculation(invoice)
    invoice.save()
    return invoice


def generate_invoice_files(invoice, save_docx=True):
    """Render and attach the PDF (and optionally DOCX) for one invoice."""
    from invoices.models import Invoice

    try:
        context = get_invoice_context(invoice)
        pdf_bytes = build_invoice_pdf(context)
        invoice.pdf_file.save(invoice.pdf_filename, ContentFile(pdf_bytes), save=False)

        if save_docx:
            docx_bytes = build_invoice_docx(context)
            invoice.docx_file.save(invoice.docx_filename, ContentFile(docx_bytes), save=False)

        invoice.status = Invoice.STATUS_GENERATED
        invoice.error_message = ''
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception('Failed to generate files for invoice %s', invoice.invoice_number)
        invoice.status = Invoice.STATUS_FAILED
        invoice.error_message = str(exc)[:500]
    invoice.save()
    return invoice


def process_batch_rows(batch, processed_rows, user):
    """Generate one invoice per valid processed row and track batch counters."""
    from invoices.models import Invoice

    generated, failed = 0, 0
    for row in processed_rows:
        try:
            invoice = create_invoice_from_row(row.data, batch=batch, user=user)
            invoice = generate_invoice_files(invoice)
            if invoice.status == Invoice.STATUS_GENERATED:
                generated += 1
            else:
                failed += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception('Failed to create invoice for row %s', row.row_number)
            failed += 1

    batch.generated_count = generated
    batch.failed_count = failed
    batch.status = batch.STATUS_COMPLETED
    batch.save(update_fields=['generated_count', 'failed_count', 'status'])
    return generated, failed
