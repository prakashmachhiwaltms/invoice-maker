from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from invoices.models import Invoice, InvoiceBatch


@login_required
def index(request):
    today = timezone.localdate()

    totals = Invoice.objects.aggregate(
        taxable=Sum('taxable_value'), tax=Sum('tax_amount'), total=Sum('total'),
    )

    context = {
        'total_invoices': Invoice.objects.count(),
        'invoices_today': Invoice.objects.filter(created_at__date=today).count(),
        'total_batches': InvoiceBatch.objects.count(),
        'total_taxable_value': totals['taxable'] or 0,
        'total_tax': totals['tax'] or 0,
        'total_invoice_value': totals['total'] or 0,
        'generated_count': Invoice.objects.filter(status=Invoice.STATUS_GENERATED).count(),
        'failed_count': Invoice.objects.filter(status=Invoice.STATUS_FAILED).count(),
        'recent_invoices': Invoice.objects.select_related('batch', 'created_by').order_by('-created_at')[:8],
        'recent_batches': InvoiceBatch.objects.select_related('created_by').order_by('-created_at')[:6],
    }
    return render(request, 'dashboard/index.html', context)
