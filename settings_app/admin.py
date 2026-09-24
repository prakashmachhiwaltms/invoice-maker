from django.contrib import admin

from .models import CompanySettings, InvoiceSettings, Signature


@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'gstin', 'state', 'updated_at')

    def has_add_permission(self, request):
        return not CompanySettings.objects.exists()


@admin.register(InvoiceSettings)
class InvoiceSettingsAdmin(admin.ModelAdmin):
    list_display = ('invoice_title', 'invoice_to', 'default_tax_rate', 'updated_at')

    def has_add_permission(self, request):
        return not InvoiceSettings.objects.exists()


@admin.register(Signature)
class SignatureAdmin(admin.ModelAdmin):
    list_display = ('slot', 'label', 'is_active', 'uploaded_at')
