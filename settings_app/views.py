from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import admin_required
from accounts.models import ActivityLog

from .forms import CompanySettingsForm, InvoiceSettingsForm, SignatureUploadForm
from .models import CompanySettings, InvoiceSettings, Signature


@admin_required
def company_settings_view(request):
    instance = CompanySettings.get_solo()
    form = CompanySettingsForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        form.save()
        ActivityLog.log(request.user, 'Company settings changed', request=request)
        messages.success(request, 'Company settings updated. New invoices will use the updated details.')
        return redirect('settings_app:company')
    return render(request, 'settings/company_settings.html', {'form': form})


@admin_required
def invoice_settings_view(request):
    instance = InvoiceSettings.get_solo()
    form = InvoiceSettingsForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        form.save()
        ActivityLog.log(request.user, 'Invoice settings changed', request=request)
        messages.success(request, 'Invoice settings updated.')
        return redirect('settings_app:invoice')
    return render(request, 'settings/invoice_settings.html', {'form': form})


@admin_required
def signatures_view(request):
    sig1 = Signature.objects.filter(slot=1).first()
    sig2 = Signature.objects.filter(slot=2).first()

    if request.method == 'POST':
        slot = int(request.POST.get('slot', 0))
        instance = Signature.objects.filter(slot=slot).first()
        form = SignatureUploadForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            ActivityLog.log(request.user, 'Signature changed', description=f'slot {slot}', request=request)
            messages.success(request, f'Signature {slot} updated.')
            return redirect('settings_app:signatures')
        else:
            messages.error(request, 'Please correct the errors below.')
            form1 = form if slot == 1 else SignatureUploadForm(instance=sig1, initial={'slot': 1})
            form2 = form if slot == 2 else SignatureUploadForm(instance=sig2, initial={'slot': 2})
            return render(request, 'settings/signatures.html', {
                'form1': form1, 'form2': form2, 'sig1': sig1, 'sig2': sig2,
            })

    form1 = SignatureUploadForm(instance=sig1, initial={'slot': 1})
    form2 = SignatureUploadForm(instance=sig2, initial={'slot': 2})
    return render(request, 'settings/signatures.html', {
        'form1': form1, 'form2': form2, 'sig1': sig1, 'sig2': sig2,
    })


@admin_required
def signature_delete(request, slot):
    sig = get_object_or_404(Signature, slot=slot)
    if request.method == 'POST':
        sig.delete()
        ActivityLog.log(request.user, 'Signature removed', description=f'slot {slot}', request=request)
        messages.success(request, f'Signature {slot} removed.')
    return redirect('settings_app:signatures')
