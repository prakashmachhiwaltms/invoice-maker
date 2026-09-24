import os

from django import forms
from django.conf import settings

from .models import Invoice


class UploadForm(forms.Form):
    file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls,.csv'})
    )

    def clean_file(self):
        f = self.cleaned_data['file']
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
            raise forms.ValidationError('Unsupported file type. Please upload a .xlsx, .xls or .csv file.')
        if f.size > settings.MAX_UPLOAD_SIZE_BYTES:
            raise forms.ValidationError('File is too large. Maximum allowed size is 10 MB.')
        return f


class InvoiceEditForm(forms.ModelForm):
    invoice_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))

    class Meta:
        model = Invoice
        fields = [
            'invoice_number', 'invoice_date', 'invoice_to',
            'supplier_name', 'supplier_address', 'country', 'state', 'state_code',
            'place_of_supply', 'supplier_gstin',
            'description', 'hsn', 'quantity',
            'total_value', 'discount', 'taxable_value',
            'tax_type', 'tax_rate', 'tax_amount',
            'freight', 'insurance', 'packing',
        ]
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'invoice_to': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_name': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'state_code': forms.TextInput(attrs={'class': 'form-control'}),
            'place_of_supply': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_gstin': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'hsn': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'total_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'taxable_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax_type': forms.Select(attrs={'class': 'form-select'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'tax_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'freight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'insurance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'packing': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class ManualInvoiceForm(InvoiceEditForm):
    pass
