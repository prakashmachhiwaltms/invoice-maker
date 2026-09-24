from .models import CompanySettings, InvoiceSettings


def company_settings(request):
    try:
        company = CompanySettings.get_solo()
        invoice_settings = InvoiceSettings.get_solo()
    except Exception:
        company, invoice_settings = None, None
    return {
        'global_company_settings': company,
        'global_invoice_settings': invoice_settings,
    }
