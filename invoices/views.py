from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import admin_required
from accounts.models import ActivityLog

from .forms import InvoiceEditForm, ManualInvoiceForm, UploadForm
from .models import Invoice, InvoiceBatch
from .services.excel_processor import process_spreadsheet
from .services.export import build_error_report_csv, build_invoices_csv
from .services.invoice_generator import (
    apply_tax_calculation, create_invoice_from_row, generate_invoice_files,
    get_invoice_context, process_batch_rows,
)
from .services.zip_generator import build_zip

CACHE_TTL = 60 * 60 * 6  # 6 hours


def _cache_key(batch_id):
    return f'invoice_batch_process_result:{batch_id}'


def _get_or_reprocess(batch):
    result = cache.get(_cache_key(batch.pk))
    if result is not None:
        return result
    existing = Invoice.objects.exclude(batch=batch).values_list('invoice_number', flat=True)
    batch.source_file.open('rb')
    try:
        result = process_spreadsheet(batch.source_file, batch.original_filename, existing_invoice_numbers=existing)
    finally:
        batch.source_file.close()
    cache.set(_cache_key(batch.pk), result, CACHE_TTL)
    return result


def can_edit_invoice(user, invoice):
    profile = getattr(user, 'profile', None)
    return user.is_superuser or (profile and profile.is_admin) or invoice.created_by_id == user.id


def is_admin_user(user):
    profile = getattr(user, 'profile', None)
    return user.is_superuser or (profile and profile.is_admin)


# ---------------------------------------------------------------------------
# Upload / Batch generation
# ---------------------------------------------------------------------------

@login_required
def upload_view(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        uploaded = form.cleaned_data['file']
        batch = InvoiceBatch.objects.create(
            source_file=uploaded, original_filename=uploaded.name, created_by=request.user,
        )
        existing = Invoice.objects.values_list('invoice_number', flat=True)
        batch.source_file.open('rb')
        try:
            result = process_spreadsheet(batch.source_file, batch.original_filename, existing_invoice_numbers=existing)
        finally:
            batch.source_file.close()

        if result.global_error:
            batch.status = InvoiceBatch.STATUS_FAILED
            batch.error_summary = [result.global_error]
            batch.save()
            messages.error(request, result.global_error)
            ActivityLog.log(request.user, 'Excel upload failed', obj=batch, description=result.global_error, request=request)
            return redirect('invoices:upload')

        cache.set(_cache_key(batch.pk), result, CACHE_TTL)
        batch.total_rows = result.total_rows
        batch.valid_rows = len(result.valid_rows)
        batch.invalid_rows = len(result.invalid_rows)

        if result.invalid_rows:
            from django.core.files.base import ContentFile
            csv_content = build_error_report_csv(result.invalid_rows)
            batch.error_report.save(f'batch_{batch.pk}_errors.csv', ContentFile(csv_content.encode('utf-8')), save=False)

        batch.save()
        ActivityLog.log(request.user, 'Excel uploaded', obj=batch, description=batch.original_filename, request=request)
        messages.success(request, f'File processed: {batch.valid_rows} valid row(s), {batch.invalid_rows} invalid row(s).')
        return redirect('invoices:batch_preview', pk=batch.pk)

    return render(request, 'invoices/upload.html', {'form': form})


@login_required
def batch_preview(request, pk):
    batch = get_object_or_404(InvoiceBatch, pk=pk)
    result = _get_or_reprocess(batch)
    return render(request, 'invoices/batch_preview.html', {
        'batch': batch,
        'result': result,
        'valid_rows': result.valid_rows,
        'invalid_rows': result.invalid_rows,
    })


@login_required
def batch_generate(request, pk):
    batch = get_object_or_404(InvoiceBatch, pk=pk)
    if request.method != 'POST':
        return redirect('invoices:batch_preview', pk=batch.pk)

    if batch.status == InvoiceBatch.STATUS_COMPLETED:
        messages.info(request, 'This batch has already been generated.')
        return redirect('invoices:batch_detail', pk=batch.pk)

    result = _get_or_reprocess(batch)
    batch.status = InvoiceBatch.STATUS_PROCESSING
    batch.save(update_fields=['status'])

    generated, failed = process_batch_rows(batch, result.valid_rows, request.user)
    cache.delete(_cache_key(batch.pk))

    ActivityLog.log(request.user, 'Batch generated', obj=batch,
                     description=f'{generated} generated, {failed} failed', request=request)
    messages.success(request, f'Invoice generation complete: {generated} generated, {failed} failed.')
    return redirect('invoices:batch_detail', pk=batch.pk)


@login_required
def batch_list(request):
    batches = InvoiceBatch.objects.select_related('created_by').all()
    paginator = Paginator(batches, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'invoices/batch_list.html', {'page_obj': page_obj})


@login_required
def batch_detail(request, pk):
    batch = get_object_or_404(InvoiceBatch, pk=pk)
    invoices = batch.invoices.all().order_by('invoice_number')
    return render(request, 'invoices/batch_detail.html', {'batch': batch, 'invoices': invoices})


@admin_required
def batch_delete(request, pk):
    batch = get_object_or_404(InvoiceBatch, pk=pk)
    if request.method == 'POST':
        name = batch.original_filename
        cache.delete(_cache_key(batch.pk))
        batch.delete()
        ActivityLog.log(request.user, 'Batch deleted', description=name, request=request)
        messages.success(request, f'Batch "{name}" and its invoices were deleted.')
        return redirect('invoices:batch_list')
    return render(request, 'invoices/batch_confirm_delete.html', {'batch': batch})


@login_required
def batch_regenerate_failed(request, pk):
    batch = get_object_or_404(InvoiceBatch, pk=pk)
    if request.method != 'POST':
        return redirect('invoices:batch_detail', pk=pk)
    failed_invoices = batch.invoices.filter(status=Invoice.STATUS_FAILED)
    count = 0
    for invoice in failed_invoices:
        generate_invoice_files(invoice)
        if invoice.status == Invoice.STATUS_GENERATED:
            count += 1
    batch.generated_count = batch.invoices.filter(status=Invoice.STATUS_GENERATED).count()
    batch.failed_count = batch.invoices.filter(status=Invoice.STATUS_FAILED).count()
    batch.save(update_fields=['generated_count', 'failed_count'])
    messages.success(request, f'Regenerated {count} of {failed_invoices.count()} failed invoice(s).')
    return redirect('invoices:batch_detail', pk=batch.pk)


@login_required
def batch_download_error_report(request, pk):
    batch = get_object_or_404(InvoiceBatch, pk=pk)
    if not batch.error_report:
        messages.info(request, 'No error report is available for this batch.')
        return redirect('invoices:batch_detail', pk=batch.pk)
    batch.error_report.open('rb')
    response = HttpResponse(batch.error_report.read(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="batch_{batch.pk}_errors.csv"'
    batch.error_report.close()
    return response


@login_required
def batch_download_zip(request, pk):
    batch = get_object_or_404(InvoiceBatch, pk=pk)
    invoices = batch.invoices.filter(status=Invoice.STATUS_GENERATED)
    zip_bytes = build_zip(invoices, file_type='pdf')
    response = HttpResponse(zip_bytes, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="batch_{batch.pk}_invoices.zip"'
    return response


@login_required
def batch_download_all_pdf(request, pk):
    return batch_download_zip(request, pk)


@login_required
def batch_download_all_docx(request, pk):
    batch = get_object_or_404(InvoiceBatch, pk=pk)
    invoices = batch.invoices.filter(status=Invoice.STATUS_GENERATED)
    zip_bytes = build_zip(invoices, file_type='docx')
    response = HttpResponse(zip_bytes, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="batch_{batch.pk}_invoices_docx.zip"'
    return response


@login_required
def batch_download_csv(request, pk):
    batch = get_object_or_404(InvoiceBatch, pk=pk)
    csv_content = build_invoices_csv(batch.invoices.all().order_by('invoice_number'))
    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="batch_{batch.pk}_invoices.csv"'
    return response


# ---------------------------------------------------------------------------
# Invoice history / CRUD
# ---------------------------------------------------------------------------

@login_required
def invoice_list(request):
    invoices = Invoice.objects.select_related('batch', 'created_by').all()

    q = request.GET.get('q', '').strip()
    if q:
        invoices = invoices.filter(Q(invoice_number__icontains=q) | Q(supplier_name__icontains=q))

    status = request.GET.get('status')
    if status:
        invoices = invoices.filter(status=status)

    batch_id = request.GET.get('batch')
    if batch_id:
        invoices = invoices.filter(batch_id=batch_id)

    created_by = request.GET.get('created_by')
    if created_by:
        invoices = invoices.filter(created_by_id=created_by)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        invoices = invoices.filter(invoice_date__gte=date_from)
    if date_to:
        invoices = invoices.filter(invoice_date__lte=date_to)

    paginator = Paginator(invoices, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    from django.contrib.auth.models import User
    return render(request, 'invoices/invoice_list.html', {
        'page_obj': page_obj,
        'query': q,
        'status': status or '',
        'batches': InvoiceBatch.objects.order_by('-created_at')[:50],
        'users': User.objects.all(),
        'status_choices': Invoice.STATUS_CHOICES,
    })


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    return render(request, 'invoices/invoice_detail.html', {'invoice': invoice})


@login_required
def invoice_create(request):
    form = ManualInvoiceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        invoice = form.save(commit=False)
        invoice.created_by = request.user
        invoice.status = Invoice.STATUS_PENDING
        apply_tax_calculation(invoice)
        invoice.save()
        generate_invoice_files(invoice)
        ActivityLog.log(request.user, 'Invoice created', obj=invoice, description=invoice.invoice_number, request=request)
        messages.success(request, f'Invoice {invoice.invoice_number} created.')
        return redirect('invoices:invoice_detail', pk=invoice.pk)
    return render(request, 'invoices/invoice_form.html', {'form': form, 'is_create': True})


@login_required
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if not can_edit_invoice(request.user, invoice):
        return HttpResponseForbidden('You do not have permission to edit this invoice.')

    form = InvoiceEditForm(request.POST or None, instance=invoice)
    if request.method == 'POST' and form.is_valid():
        updated = form.save(commit=False)
        apply_tax_calculation(updated)
        updated.save()
        regenerate = 'save_regenerate' in request.POST
        if regenerate:
            generate_invoice_files(updated)
            messages.success(request, f'Invoice {updated.invoice_number} saved and PDF/DOCX regenerated.')
        else:
            messages.success(request, f'Invoice {updated.invoice_number} saved.')
        ActivityLog.log(request.user, 'Invoice updated', obj=updated, description=updated.invoice_number, request=request)
        return redirect('invoices:invoice_detail', pk=updated.pk)
    return render(request, 'invoices/invoice_form.html', {'form': form, 'is_create': False, 'invoice': invoice})


@login_required
def invoice_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if not can_edit_invoice(request.user, invoice):
        return HttpResponseForbidden('You do not have permission to delete this invoice.')
    if request.method == 'POST':
        number = invoice.invoice_number
        invoice.delete()
        ActivityLog.log(request.user, 'Invoice deleted', description=number, request=request)
        messages.success(request, f'Invoice {number} deleted.')
        return redirect('invoices:invoice_list')
    return render(request, 'invoices/invoice_confirm_delete.html', {'invoice': invoice})


@login_required
def invoice_regenerate(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method != 'POST':
        return redirect('invoices:invoice_detail', pk=pk)
    generate_invoice_files(invoice)
    ActivityLog.log(request.user, 'Invoice regenerated', obj=invoice, description=invoice.invoice_number, request=request)
    messages.success(request, f'Invoice {invoice.invoice_number} regenerated.')
    return redirect('invoices:invoice_detail', pk=invoice.pk)


@login_required
def invoice_preview(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    return render(request, 'invoices/invoice_preview.html', {'invoice': invoice})


@login_required
def invoice_preview_raw(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    context = get_invoice_context(invoice)
    return render(request, 'invoices/rcm_invoice.html', context)


@login_required
def invoice_download_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if not invoice.pdf_file:
        messages.error(request, 'PDF has not been generated for this invoice yet.')
        return redirect('invoices:invoice_detail', pk=pk)
    invoice.pdf_file.open('rb')
    response = HttpResponse(invoice.pdf_file.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{invoice.pdf_filename}"'
    invoice.pdf_file.close()
    ActivityLog.log(request.user, 'Invoice PDF downloaded', obj=invoice, description=invoice.invoice_number, request=request)
    return response


@login_required
def invoice_download_docx(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if not invoice.docx_file:
        messages.error(request, 'DOCX has not been generated for this invoice yet.')
        return redirect('invoices:invoice_detail', pk=pk)
    invoice.docx_file.open('rb')
    response = HttpResponse(
        invoice.docx_file.read(),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    response['Content-Disposition'] = f'attachment; filename="{invoice.docx_filename}"'
    invoice.docx_file.close()
    ActivityLog.log(request.user, 'Invoice DOCX downloaded', obj=invoice, description=invoice.invoice_number, request=request)
    return response


# ---------------------------------------------------------------------------
# Bulk export
# ---------------------------------------------------------------------------

def _selected_invoices(request):
    raw_values = request.POST.getlist('invoice_ids') or request.GET.getlist('invoice_ids')
    ids = []
    for raw in raw_values:
        ids.extend(i for i in str(raw).split(',') if i)
    return Invoice.objects.filter(pk__in=ids)


@login_required
def bulk_download_zip(request):
    invoices = _selected_invoices(request)
    file_type = request.GET.get('type', request.POST.get('type', 'pdf'))
    zip_bytes = build_zip(invoices, file_type=file_type)
    response = HttpResponse(zip_bytes, content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="invoices.zip"'
    return response


@login_required
def bulk_download_csv(request):
    invoices = _selected_invoices(request)
    if not invoices.exists():
        invoices = Invoice.objects.all()
    csv_content = build_invoices_csv(invoices)
    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="invoices_export.csv"'
    return response


@admin_required
def bulk_delete(request):
    if request.method == 'POST':
        invoices = _selected_invoices(request)
        count = invoices.count()
        invoices.delete()
        ActivityLog.log(request.user, 'Bulk invoice delete', description=f'{count} invoice(s)', request=request)
        messages.success(request, f'Deleted {count} invoice(s).')
    return redirect('invoices:invoice_list')
