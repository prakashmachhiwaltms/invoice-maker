import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import ActivityLog

from .forms import PdfFindReplaceForm, PdfUploadForm
from .models import (
    PdfBatch, PdfDocument, PdfField, PdfReplacementRule, PdfReplacementRuleLabel,
    PdfReplacementRuleSet, PdfVersion,
)
from .services import bulk as bulk_service
from .services import document_service, extraction, field_service, label_rule_engine, zip_export
from .services.security import can_access_document, is_admin_user
from .services.upload import create_batch_from_files


def _visible_documents(user):
    qs = PdfDocument.objects.select_related('batch', 'current_version', 'uploaded_by')
    if not is_admin_user(user):
        qs = qs.filter(uploaded_by=user)
    return qs


def _visible_batches(user):
    qs = PdfBatch.objects.select_related('created_by')
    if not is_admin_user(user):
        qs = qs.filter(created_by=user)
    return qs


def _get_accessible_document(request, pk):
    document = get_object_or_404(PdfDocument.objects.select_related('current_version', 'batch'), pk=pk)
    if not can_access_document(request.user, document):
        return None
    return document


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard_view(request):
    documents = _visible_documents(request.user)
    batches = _visible_batches(request.user)
    context = {
        'total_batches': batches.count(),
        'total_pdfs': documents.count(),
        'ready_count': documents.filter(status=PdfDocument.STATUS_READY).count(),
        'edited_count': documents.filter(current_version__version_number__gt=1).count(),
        'failed_count': documents.filter(status=PdfDocument.STATUS_FAILED).count(),
        'recent_batches': batches.order_by('-created_at')[:6],
        'recent_edited': documents.filter(current_version__version_number__gt=1).order_by('-updated_at')[:8],
    }
    return render(request, 'pdf_editor/dashboard.html', context)


# ---------------------------------------------------------------------------
# Upload / Library / Batches
# ---------------------------------------------------------------------------

@login_required
def upload_view(request):
    form = PdfUploadForm(request.POST or None)
    if request.method == 'POST':
        files = request.FILES.getlist('files')
        if not files:
            messages.error(request, 'Please choose at least one PDF file.')
        elif form.is_valid():
            batch, created, errors = create_batch_from_files(
                files, request.user, form.cleaned_data.get('batch_name', ''),
            )
            ActivityLog.log(
                request.user, 'PDF batch uploaded', obj=batch,
                description=f'{len(created)} succeeded, {len(errors)} failed', request=request,
            )
            if created:
                messages.success(request, f'{len(created)} PDF(s) uploaded successfully.')
            for err in errors:
                messages.error(request, f'{err["filename"]}: {err["error"]}')
            return redirect('pdf_editor:batch_detail', pk=batch.pk)
    return render(request, 'pdf_editor/upload.html', {'form': form})


@login_required
def library_view(request):
    documents = _visible_documents(request.user)

    q = request.GET.get('q', '').strip()
    if q:
        documents = documents.filter(filename__icontains=q)

    status = request.GET.get('status')
    if status:
        documents = documents.filter(status=status)

    batch_id = request.GET.get('batch')
    if batch_id:
        documents = documents.filter(batch_id=batch_id)

    edited_only = request.GET.get('edited') == '1'
    if edited_only:
        documents = documents.filter(current_version__version_number__gt=1)

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'pdf_editor/library.html', {
        'page_obj': page_obj, 'query': q, 'status': status, 'edited_only': edited_only,
    })


@login_required
def batch_list(request):
    batches = _visible_batches(request.user).annotate(
        edited_count=Count('documents', filter=Q(documents__current_version__version_number__gt=1), distinct=True),
    )

    q = request.GET.get('q', '').strip()
    if q:
        batches = batches.filter(name__icontains=q)

    status = request.GET.get('status')
    if status:
        batches = batches.filter(status=status)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        batches = batches.filter(created_at__date__gte=date_from)
    if date_to:
        batches = batches.filter(created_at__date__lte=date_to)

    paginator = Paginator(batches, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'pdf_editor/batch_list.html', {
        'page_obj': page_obj, 'query': q, 'status': status,
    })


@login_required
def batch_detail(request, pk):
    batch = get_object_or_404(PdfBatch, pk=pk)
    if not is_admin_user(request.user) and batch.created_by_id != request.user.id:
        return HttpResponseForbidden('You do not have access to this batch.')
    documents = batch.documents.select_related('current_version').all()
    edited_count = documents.filter(current_version__version_number__gt=1).count()
    q = request.GET.get('q', '').strip()
    if q:
        documents = documents.filter(filename__icontains=q)
    return render(request, 'pdf_editor/batch_detail.html', {
        'batch': batch, 'documents': documents, 'edited_count': edited_count, 'query': q,
    })


@login_required
def batch_delete(request, pk):
    batch = get_object_or_404(PdfBatch, pk=pk)
    if not is_admin_user(request.user) and batch.created_by_id != request.user.id:
        return HttpResponseForbidden('You do not have access to this batch.')
    if request.method == 'POST':
        name = batch.name or f'Batch #{batch.pk}'
        batch.delete()
        ActivityLog.log(request.user, 'PDF batch deleted', description=name, request=request)
        messages.success(request, f'Batch "{name}" deleted.')
        return redirect('pdf_editor:batch_list')
    return render(request, 'pdf_editor/batch_confirm_delete.html', {'batch': batch})


@login_required
def batch_download_zip(request, pk):
    batch = get_object_or_404(PdfBatch, pk=pk)
    if not is_admin_user(request.user) and batch.created_by_id != request.user.id:
        return HttpResponseForbidden('You do not have access to this batch.')
    documents = batch.documents.select_related('current_version').all()
    data = zip_export.build_batch_zip(documents)
    slug = (batch.name or f'batch-{batch.pk}').strip().lower().replace(' ', '-') or f'batch-{batch.pk}'
    ActivityLog.log(request.user, 'PDF batch ZIP downloaded', obj=batch, request=request)
    response = HttpResponse(data, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{slug}-edited-invoices.zip"'
    return response


# ---------------------------------------------------------------------------
# Document actions
# ---------------------------------------------------------------------------

@login_required
def editor_view(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('You do not have access to this document.')
    return render(request, 'pdf_editor/editor.html', {'document': document})


@login_required
def document_versions_view(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('You do not have access to this document.')
    versions = document.versions.select_related('created_by').order_by('-version_number')
    return render(request, 'pdf_editor/document_versions.html', {'document': document, 'versions': versions})


@login_required
def download_current(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('You do not have access to this document.')
    field_file = document.current_file
    field_file.open('rb')
    try:
        data = field_file.read()
    finally:
        field_file.close()
    version_no = document.current_version.version_number if document.current_version_id else 1
    base_name = document.filename[:-4] if document.filename.lower().endswith('.pdf') else document.filename
    suffix = '' if version_no == 1 else f'_edited_v{version_no}'
    response = HttpResponse(data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{base_name}{suffix}.pdf"'
    return response


@login_required
def download_version(request, pk, version_number):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('You do not have access to this document.')
    version = get_object_or_404(PdfVersion, document=document, version_number=version_number)
    version.file.open('rb')
    try:
        data = version.file.read()
    finally:
        version.file.close()
    base_name = document.filename[:-4] if document.filename.lower().endswith('.pdf') else document.filename
    response = HttpResponse(data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{base_name}_v{version_number}.pdf"'
    return response


@login_required
def duplicate_document(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('You do not have access to this document.')
    if request.method == 'POST':
        field_file = document.current_file
        field_file.open('rb')
        try:
            data = field_file.read()
        finally:
            field_file.close()
        new_doc = PdfDocument.objects.create(
            batch=document.batch, original_file=ContentFile(data, name=document.filename),
            filename=document.filename, uploaded_by=request.user,
            page_count=document.page_count, has_extractable_text=document.has_extractable_text,
            status=document.status,
        )
        version = PdfVersion.objects.create(
            document=new_doc, version_number=1, file=ContentFile(data, name=document.filename),
            note=f'Duplicated from "{document.filename}"', created_by=request.user,
        )
        new_doc.current_version = version
        new_doc.save(update_fields=['current_version'])
        ActivityLog.log(request.user, 'PDF duplicated', obj=new_doc, description=document.filename, request=request)
        messages.success(request, f'"{document.filename}" duplicated.')
        return redirect('pdf_editor:library')
    return redirect('pdf_editor:library')


@login_required
def delete_document(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('You do not have access to this document.')
    if request.method == 'POST':
        name = document.filename
        document.delete()
        ActivityLog.log(request.user, 'PDF deleted', description=name, request=request)
        messages.success(request, f'"{name}" deleted.')
        return redirect('pdf_editor:library')
    return render(request, 'pdf_editor/document_confirm_delete.html', {'document': document})


# ---------------------------------------------------------------------------
# Editor JSON API
# ---------------------------------------------------------------------------

def _build_page_payload(document, page_number):
    page_index = page_number - 1
    doc = document_service.open_fitz(document)
    blocks = extraction.get_page_text_blocks(doc, page_index)
    _, width, height = extraction.render_page_png(doc, page_index)
    page_rect = doc[page_index].rect
    version_no = document.current_version.version_number if document.current_version_id else 1
    return {
        'page': page_number,
        'page_count': document.page_count,
        'image_url': reverse('pdf_editor:api_page_image', args=[document.pk, page_number]) + f'?v={version_no}',
        'image_width': width,
        'image_height': height,
        'page_width_pt': page_rect.width,
        'page_height_pt': page_rect.height,
        'blocks': blocks,
        'version_number': version_no,
        'has_extractable_text': document.has_extractable_text,
        'can_undo': version_no > 1,
        'can_redo': PdfVersion.objects.filter(document=document, version_number=version_no + 1).exists(),
    }


@login_required
def api_page_data(request, pk, page_number):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    if page_number < 1 or page_number > document.page_count:
        return HttpResponseBadRequest('Invalid page number')
    return JsonResponse(_build_page_payload(document, page_number))


@login_required
def api_page_image(request, pk, page_number):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    if page_number < 1 or page_number > document.page_count:
        return HttpResponseBadRequest('Invalid page number')
    doc = document_service.open_fitz(document)
    png_bytes, _, _ = extraction.render_page_png(doc, page_number - 1)
    return HttpResponse(png_bytes, content_type='image/png')


@require_POST
@login_required
def api_replace(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    body = _json_body(request)
    page_number = int(body.get('page', 1))
    span_id = body.get('span_id')
    new_text = body.get('new_text', '')
    if not span_id:
        return HttpResponseBadRequest('span_id is required')
    try:
        document_service.apply_replace(document, request.user, page_number - 1, span_id, new_text)
    except document_service.SpanNotFound:
        return HttpResponseBadRequest('That text block no longer exists on this page. Please reload.')
    document.refresh_from_db()
    ActivityLog.log(request.user, 'PDF text replaced', obj=document, description=new_text[:100], request=request)
    return JsonResponse(_build_page_payload(document, page_number))


@require_POST
@login_required
def api_hide(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    body = _json_body(request)
    page_number = int(body.get('page', 1))
    span_id = body.get('span_id')
    if not span_id:
        return HttpResponseBadRequest('span_id is required')
    try:
        document_service.apply_hide(document, request.user, page_number - 1, span_id)
    except document_service.SpanNotFound:
        return HttpResponseBadRequest('That text block no longer exists on this page. Please reload.')
    document.refresh_from_db()
    ActivityLog.log(request.user, 'PDF text hidden', obj=document, request=request)
    return JsonResponse(_build_page_payload(document, page_number))


@require_POST
@login_required
def api_move(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    body = _json_body(request)
    page_number = int(body.get('page', 1))
    span_id = body.get('span_id')
    if not span_id:
        return HttpResponseBadRequest('span_id is required')
    try:
        new_x = float(body.get('x'))
        new_y = float(body.get('y'))
    except (TypeError, ValueError):
        return HttpResponseBadRequest('x and y are required numbers')
    try:
        document_service.apply_move(document, request.user, page_number - 1, span_id, new_x, new_y)
    except document_service.SpanNotFound:
        return HttpResponseBadRequest('That text block no longer exists on this page. Please reload.')
    document.refresh_from_db()
    ActivityLog.log(request.user, 'PDF text moved', obj=document, request=request)
    return JsonResponse(_build_page_payload(document, page_number))


@require_POST
@login_required
def api_add_text(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    body = _json_body(request)
    page_number = int(body.get('page', 1))
    text = (body.get('text') or '').strip()
    if not text:
        return HttpResponseBadRequest('text is required')
    try:
        x = float(body.get('x'))
        y = float(body.get('y'))
    except (TypeError, ValueError):
        return HttpResponseBadRequest('x and y are required numbers')
    font_size = float(body.get('font_size', 11) or 11)
    bold = bool(body.get('bold'))
    italic = bool(body.get('italic'))
    document_service.apply_add_text(document, request.user, page_number - 1, x, y, text, font_size, bold, italic)
    document.refresh_from_db()
    ActivityLog.log(request.user, 'PDF text added', obj=document, description=text[:100], request=request)
    return JsonResponse(_build_page_payload(document, page_number))


@require_POST
@login_required
def api_undo(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    body = _json_body(request)
    page_number = int(body.get('page', 1))
    ok = document_service.undo(document)
    document.refresh_from_db()
    payload = _build_page_payload(document, page_number)
    payload['undone'] = ok
    return JsonResponse(payload)


@require_POST
@login_required
def api_redo(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    body = _json_body(request)
    page_number = int(body.get('page', 1))
    ok = document_service.redo(document)
    document.refresh_from_db()
    payload = _build_page_payload(document, page_number)
    payload['redone'] = ok
    return JsonResponse(payload)


@login_required
def api_search(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    query = request.GET.get('q', '').strip()
    matches = document_service.search_document(document, query) if query else []
    results = [{**m, 'page': m['page'] + 1} for m in matches]
    return JsonResponse({'query': query, 'count': len(results), 'matches': results})


@require_POST
@login_required
def api_replace_all(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    body = _json_body(request)
    find_text = (body.get('find_text') or '').strip()
    replace_text = body.get('replace_text', '')
    page_number = int(body.get('page', 1))
    if not find_text:
        return HttpResponseBadRequest('find_text is required')
    version, count = document_service.apply_replace_all(document, request.user, find_text, replace_text)
    document.refresh_from_db()
    ActivityLog.log(
        request.user, 'PDF replace-all', obj=document,
        description=f'"{find_text}" -> "{replace_text}" ({count})', request=request,
    )
    payload = _build_page_payload(document, page_number)
    payload['replaced_count'] = count
    return JsonResponse(payload)


# ---------------------------------------------------------------------------
# Cross-document (batch / selected) Find & Replace
# ---------------------------------------------------------------------------

def _resolve_scope_documents(user, cleaned):
    scope = cleaned['scope']
    base = _visible_documents(user)
    if scope == 'batch':
        batch_id = cleaned.get('batch_id')
        if not batch_id:
            return []
        return list(base.filter(batch_id=batch_id))
    ids = [i for i in (cleaned.get('document_ids') or '').split(',') if i.strip().isdigit()]
    if not ids:
        return []
    return list(base.filter(pk__in=ids))


@login_required
def find_replace_view(request):
    initial = {}
    preselect_document = request.GET.get('document')
    preselect_ids = request.GET.get('document_ids')
    preselect_batch = request.GET.get('batch')
    if preselect_document:
        initial = {'scope': 'current', 'document_ids': preselect_document}
    elif preselect_ids:
        initial = {'scope': 'selected', 'document_ids': preselect_ids}
    elif preselect_batch:
        initial = {'scope': 'batch', 'batch_id': preselect_batch}
    form = PdfFindReplaceForm(request.POST or None, initial=initial)
    preview_rows = None
    if request.method == 'POST' and form.is_valid():
        documents = _resolve_scope_documents(request.user, form.cleaned_data)
        if not documents:
            messages.error(request, 'No PDFs matched that scope.')
        else:
            preview_rows = bulk_service.preview_bulk_replace(documents, form.cleaned_data['find_text'])
    return render(request, 'pdf_editor/find_replace.html', {
        'form': form,
        'preview_rows': preview_rows,
        'matched_count': sum(1 for r in preview_rows if r.match_count) if preview_rows else 0,
        'batches': _visible_batches(request.user),
    })


@require_POST
@login_required
def find_replace_apply(request):
    form = PdfFindReplaceForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Invalid find & replace request.')
        return redirect('pdf_editor:find_replace')
    documents = _resolve_scope_documents(request.user, form.cleaned_data)
    if not documents:
        messages.error(request, 'No PDFs matched that scope.')
        return redirect('pdf_editor:find_replace')
    affected, total = bulk_service.apply_bulk_replace(
        documents, form.cleaned_data['find_text'], form.cleaned_data.get('replace_text', ''), request.user,
    )
    ActivityLog.log(
        request.user, 'PDF bulk find & replace',
        description=f'{affected} PDF(s), {total} replacement(s)', request=request,
    )
    messages.success(request, f'Applied to {affected} PDF(s), {total} replacement(s) made.')
    return redirect('pdf_editor:library')


# ---------------------------------------------------------------------------
# Label & Value Editor
# ---------------------------------------------------------------------------

def _ordered_fields(document, include_rejected=False):
    qs = document.fields.all() if include_rejected else document.fields.exclude(status=PdfField.STATUS_REJECTED)
    fields = list(qs)
    fields.sort(key=lambda f: (f.page, (f.label_bbox or {}).get('y', 0), (f.label_bbox or {}).get('x', 0)))
    return fields


def _build_field_payload(field):
    return {
        'id': field.pk, 'page': field.page + 1,
        'label': field.label, 'value': field.value, 'separator': field.separator,
        'original_label': field.original_label, 'original_value': field.original_value,
        'original_separator': field.original_separator,
        'label_bbox': field.label_bbox, 'value_bbox': field.value_bbox,
        'font': field.font, 'font_size': field.font_size, 'font_weight': field.font_weight, 'color': field.color,
        'confidence': field.confidence, 'confidence_display': field.confidence_display,
        'status': field.status, 'status_display': field.get_status_display(), 'is_manual': field.is_manual,
    }


@login_required
def label_editor_view(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('You do not have access to this document.')
    if document.has_extractable_text:
        field_service.sync_detected_fields(document)
    return render(request, 'pdf_editor/label_editor.html', {'document': document})


@login_required
def api_fields_list(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    if document.has_extractable_text:
        field_service.sync_detected_fields(document)
    fields = _ordered_fields(document)
    high = sum(1 for f in fields if f.confidence == PdfField.CONFIDENCE_HIGH)
    version_no = document.current_version.version_number if document.current_version_id else 1
    return JsonResponse({
        'has_extractable_text': document.has_extractable_text,
        'total': len(fields), 'high_confidence': high, 'needs_review': len(fields) - high,
        'version_number': version_no, 'can_undo': version_no > 1,
        'can_redo': PdfVersion.objects.filter(document=document, version_number=version_no + 1).exists(),
        'fields': [_build_field_payload(f) for f in fields],
    })


@require_POST
@login_required
def api_fields_redetect(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    field_service.sync_detected_fields(document)
    return JsonResponse({'fields': [_build_field_payload(f) for f in _ordered_fields(document)]})


@require_POST
@login_required
def api_field_apply(request, pk, field_id):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    body = _json_body(request)
    try:
        field_service.apply_field_edit(
            document, request.user, field_id,
            body.get('label'), body.get('separator'), body.get('value'),
        )
    except field_service.FieldNotFound:
        return HttpResponseBadRequest('That field no longer exists. Please reload.')
    document.refresh_from_db()
    ActivityLog.log(request.user, 'PDF label/value edited', obj=document, description=f'field #{field_id}', request=request)
    version_no = document.current_version.version_number if document.current_version_id else 1
    return JsonResponse({
        'version_number': version_no, 'can_undo': version_no > 1,
        'can_redo': PdfVersion.objects.filter(document=document, version_number=version_no + 1).exists(),
        'fields': [_build_field_payload(f) for f in _ordered_fields(document)],
    })


@require_POST
@login_required
def api_field_confirm(request, pk, field_id):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    field = get_object_or_404(PdfField, pk=field_id, document=document)
    field_service.confirm_field(field)
    return JsonResponse(_build_field_payload(field))


@require_POST
@login_required
def api_field_reject(request, pk, field_id):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    field = get_object_or_404(PdfField, pk=field_id, document=document)
    field_service.reject_field(field)
    return JsonResponse(_build_field_payload(field))


@require_POST
@login_required
def api_field_manual_create(request, pk):
    document = _get_accessible_document(request, pk)
    if document is None:
        return HttpResponseForbidden('Forbidden')
    body = _json_body(request)
    page_number = int(body.get('page', 1))
    span_id = body.get('span_id')
    if not span_id:
        return HttpResponseBadRequest('span_id is required')
    try:
        field = field_service.create_manual_field(
            document, request.user, page_number - 1, span_id,
            body.get('label', ''), body.get('value'), body.get('separator', ':'),
        )
    except field_service.FieldNotFound:
        return HttpResponseBadRequest('That text block no longer exists on this page. Please reload.')
    ActivityLog.log(request.user, 'PDF custom field created', obj=document, description=field.label, request=request)
    return JsonResponse(_build_field_payload(field))


# ---------------------------------------------------------------------------
# Cross-document (batch / selected / current) Label & Value rule engine
# ---------------------------------------------------------------------------

def _resolve_label_documents(user, scope, batch_id, document_ids):
    """Shared by the preview/apply/discover JSON endpoints. `document_ids`
    may arrive as a comma-separated string (form-style) or a JSON list."""
    base = _visible_documents(user)
    if scope == 'batch':
        if not batch_id:
            return []
        return list(base.filter(batch_id=batch_id))
    if isinstance(document_ids, str):
        ids = [i for i in document_ids.split(',') if i.strip().isdigit()]
    else:
        ids = [str(i) for i in (document_ids or []) if str(i).isdigit()]
    if not ids:
        return []
    return list(base.filter(pk__in=ids))


@login_required
def label_editor_home(request):
    documents = _visible_documents(request.user)
    q = request.GET.get('q', '').strip()
    if q:
        documents = documents.filter(filename__icontains=q)
    paginator = Paginator(documents, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Pre-fill scope for cross-links from the batch/library pages and from
    # the per-document editor's "Apply this change to the entire batch" link.
    initial_scope, initial_batch_id, initial_document_ids = 'batch', '', ''
    preselect_batch = request.GET.get('batch')
    preselect_document = request.GET.get('document')
    preselect_ids = request.GET.get('document_ids')
    if preselect_batch:
        initial_scope, initial_batch_id = 'batch', preselect_batch
    elif preselect_document:
        initial_scope, initial_document_ids = 'current', preselect_document
    elif preselect_ids:
        initial_scope, initial_document_ids = 'selected', preselect_ids

    initial_rules = []
    label = request.GET.get('label')
    if label:
        old_value = request.GET.get('old_value', '')
        initial_rules = [{
            'labels': [label], 'match_type': 'contains' if old_value else 'any',
            'current_value': old_value, 'new_value': request.GET.get('new_value', ''),
        }]

    return render(request, 'pdf_editor/label_editor_home.html', {
        'page_obj': page_obj, 'query': q, 'batches': _visible_batches(request.user),
        'initial_scope': initial_scope, 'initial_batch_id': initial_batch_id,
        'initial_document_ids': initial_document_ids, 'initial_rules': initial_rules,
    })


def _serialize_preview(preview):
    return {
        'total_pdfs': preview.total_pdfs,
        'affected_pdfs': preview.affected_pdfs,
        'total_matches': preview.total_matches,
        'rule_summaries': preview.rule_summaries,
        'conflicts': [
            {
                'document_id': c['document'].pk, 'filename': c['document'].filename,
                'field_label': c['field'].label, 'field_value': c['field'].value,
                'rule_indices': c['rule_indices'],
            }
            for c in preview.conflicts
        ],
        'documents': [
            {
                'document_id': dp.document.pk, 'filename': dp.document.filename,
                'status': dp.status, 'skip_reason': dp.skip_reason,
                'fields': [
                    {
                        'field_id': fp['field'].pk, 'label': fp['field'].label,
                        'before': fp['before'], 'after': fp['after'],
                        'rule_index': fp['rule_index'], 'is_conflict': fp['is_conflict'],
                    }
                    for fp in dp.field_previews
                ],
            }
            for dp in preview.documents
        ],
    }


@require_POST
@login_required
def label_editor_preview(request):
    body = _json_body(request)
    documents = _resolve_label_documents(request.user, body.get('scope'), body.get('batch_id'), body.get('document_ids'))
    if not documents:
        return JsonResponse({'error': 'No PDFs matched that scope.'}, status=400)
    rules = label_rule_engine.rules_from_payload(body.get('rules'))
    if not rules:
        return JsonResponse({'error': 'Add at least one replacement rule.'}, status=400)
    preview = label_rule_engine.build_preview(documents, rules)
    return JsonResponse(_serialize_preview(preview))


@require_POST
@login_required
def label_editor_apply(request):
    body = _json_body(request)
    documents = _resolve_label_documents(request.user, body.get('scope'), body.get('batch_id'), body.get('document_ids'))
    if not documents:
        return JsonResponse({'error': 'No PDFs matched that scope.'}, status=400)
    rules = label_rule_engine.rules_from_payload(body.get('rules'))
    if not rules:
        return JsonResponse({'error': 'Add at least one replacement rule.'}, status=400)
    result = label_rule_engine.apply_rules(documents, rules, request.user)
    ActivityLog.log(
        request.user, 'PDF bulk label rules applied',
        description=(
            f'{len(rules)} rule(s): {result.affected} PDF(s) updated, '
            f'{result.skipped} skipped, {result.total_changes} field(s) changed'
        ),
        request=request,
    )
    return JsonResponse({'affected': result.affected, 'skipped': result.skipped, 'total_changes': result.total_changes})


@require_POST
@login_required
def label_editor_discover(request):
    body = _json_body(request)
    documents = _resolve_label_documents(request.user, body.get('scope'), body.get('batch_id'), body.get('document_ids'))
    if not documents:
        return JsonResponse({'error': 'No PDFs matched that scope.'}, status=400)
    rows = label_rule_engine.discover_labels(documents)
    return JsonResponse({'pdf_count': len(documents), 'labels': rows})


@login_required
def label_rule_sets(request):
    if request.method == 'POST':
        body = _json_body(request)
        name = (body.get('name') or '').strip()
        if not name:
            return HttpResponseBadRequest('name is required')
        rules = label_rule_engine.rules_from_payload(body.get('rules'))
        if not rules:
            return HttpResponseBadRequest('at least one rule is required')
        rule_set = PdfReplacementRuleSet.objects.create(name=name, created_by=request.user)
        for order, rule in enumerate(rules):
            rule_row = PdfReplacementRule.objects.create(
                rule_set=rule_set, match_type=rule.match_type, current_value=rule.current_value,
                case_sensitive=rule.case_sensitive, whitespace_normalize=rule.whitespace_normalize,
                change_label=rule.change_label, new_label=rule.new_label,
                change_separator=rule.change_separator, new_separator=rule.new_separator,
                new_value=rule.new_value, order=order,
            )
            for label_text in rule.labels:
                PdfReplacementRuleLabel.objects.create(rule=rule_row, label=label_text)
        ActivityLog.log(request.user, 'PDF label rule set saved', description=name, request=request)
        return JsonResponse({'id': rule_set.pk, 'name': rule_set.name})

    rule_sets = PdfReplacementRuleSet.objects.filter(created_by=request.user).order_by('-created_at')
    return JsonResponse({'rule_sets': [{'id': rs.pk, 'name': rs.name} for rs in rule_sets]})


@login_required
def label_rule_set_detail(request, pk):
    rule_set = get_object_or_404(PdfReplacementRuleSet, pk=pk, created_by=request.user)
    rules = []
    for rule in rule_set.rules.prefetch_related('labels').order_by('order'):
        rules.append({
            'labels': [l.label for l in rule.labels.all()],
            'match_type': rule.match_type, 'current_value': rule.current_value,
            'case_sensitive': rule.case_sensitive, 'whitespace_normalize': rule.whitespace_normalize,
            'change_label': rule.change_label, 'new_label': rule.new_label,
            'change_separator': rule.change_separator, 'new_separator': rule.new_separator,
            'new_value': rule.new_value,
        })
    return JsonResponse({'id': rule_set.pk, 'name': rule_set.name, 'rules': rules})
