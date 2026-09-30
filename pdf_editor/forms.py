from django import forms

from .models import PdfBatch


class PdfUploadForm(forms.Form):
    """File(s) themselves are read directly from request.FILES.getlist('files')
    in the view (Django has no built-in multi-file FormField); this form
    covers the batch name and an optional existing batch to add the files to."""
    batch_name = forms.CharField(required=False, max_length=255, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Optional batch name',
    }))
    existing_batch = forms.ModelChoiceField(
        queryset=PdfBatch.objects.none(), required=False, label='Add to existing batch',
        empty_label='— Create a new batch —',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            from .services.security import is_admin_user
            qs = PdfBatch.objects.all() if is_admin_user(user) else PdfBatch.objects.filter(created_by=user)
            self.fields['existing_batch'].queryset = qs.order_by('-created_at')


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


