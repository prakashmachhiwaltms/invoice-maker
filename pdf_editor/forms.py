from django import forms


class PdfUploadForm(forms.Form):
    """File(s) themselves are read directly from request.FILES.getlist('files')
    in the view (Django has no built-in multi-file FormField); this form only
    covers the optional batch name."""
    batch_name = forms.CharField(required=False, max_length=255, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Optional batch name',
    }))


PDF_FIND_REPLACE_SCOPE_CHOICES = [
    ('current', 'Current PDF'),
    ('selected', 'Selected PDFs'),
    ('batch', 'Entire Batch'),
]


class PdfFindReplaceForm(forms.Form):
    find_text = forms.CharField(label='Find', widget=forms.TextInput(attrs={'class': 'form-control'}))
    replace_text = forms.CharField(label='Replace with', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    scope = forms.ChoiceField(choices=PDF_FIND_REPLACE_SCOPE_CHOICES, widget=forms.RadioSelect)
    document_ids = forms.CharField(required=False, widget=forms.HiddenInput())
    batch_id = forms.CharField(required=False, widget=forms.HiddenInput())


