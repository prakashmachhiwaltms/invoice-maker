from django import forms

from .models import CompanySettings, InvoiceSettings, Signature


class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = ['company_name', 'company_address', 'gstin', 'state', 'state_code',
                   'place_of_supply', 'country', 'phone', 'email', 'website', 'logo']
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'company_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'gstin': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'state_code': forms.TextInput(attrs={'class': 'form-control'}),
            'place_of_supply': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'website': forms.TextInput(attrs={'class': 'form-control'}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class InvoiceSettingsForm(forms.ModelForm):
    class Meta:
        model = InvoiceSettings
        fields = ['invoice_title', 'invoice_to', 'footer_for_text', 'authorized_signatory_text',
                   'reverse_charge_note', 'default_tax_rate', 'default_hsn', 'currency', 'currency_symbol',
                   'amount_words_format', 'invoice_number_prefix', 'invoice_number_start',
                   'invoice_number_padding', 'rounding_precision']
        widgets = {
            'invoice_title': forms.TextInput(attrs={'class': 'form-control'}),
            'invoice_to': forms.TextInput(attrs={'class': 'form-control'}),
            'footer_for_text': forms.TextInput(attrs={'class': 'form-control'}),
            'authorized_signatory_text': forms.TextInput(attrs={'class': 'form-control'}),
            'reverse_charge_note': forms.TextInput(attrs={'class': 'form-control'}),
            'default_tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'default_hsn': forms.TextInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control'}),
            'currency_symbol': forms.TextInput(attrs={'class': 'form-control'}),
            'amount_words_format': forms.Select(attrs={'class': 'form-select'}),
            'invoice_number_prefix': forms.TextInput(attrs={'class': 'form-control'}),
            'invoice_number_start': forms.NumberInput(attrs={'class': 'form-control'}),
            'invoice_number_padding': forms.NumberInput(attrs={'class': 'form-control'}),
            'rounding_precision': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class SignatureUploadForm(forms.ModelForm):
    class Meta:
        model = Signature
        fields = ['slot', 'label', 'image', 'is_active']
        widgets = {
            'slot': forms.HiddenInput(),
            'label': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.png,.jpg,.jpeg,.webp'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'name'):
            ext = image.name.lower().rsplit('.', 1)[-1]
            if ext not in ('png', 'jpg', 'jpeg', 'webp'):
                raise forms.ValidationError('Only PNG, JPG, JPEG or WEBP images are allowed.')
        return image
