from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from .models import Profile


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Email or Username',
        widget=forms.TextInput(attrs={'class': 'form-control', 'autofocus': True, 'placeholder': 'Email or username'}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
    )
    remember_me = forms.BooleanField(required=False, initial=True, label='Remember me')


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
            Profile.objects.update_or_create(
                user=user,
                defaults={'role': self.cleaned_data['role'], 'phone': self.cleaned_data.get('phone', '')},
            )
        return user


class UserEditForm(forms.ModelForm):
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    is_active = forms.BooleanField(required=False, label='Active')

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            Profile.objects.update_or_create(
                user=user,
                defaults={'role': self.cleaned_data['role'], 'phone': self.cleaned_data.get('phone', '')},
            )
        return user


class AdminSetPasswordForm(forms.Form):
    new_password1 = forms.CharField(label='New password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    new_password2 = forms.CharField(label='Confirm new password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('new_password1'), cleaned.get('new_password2')
        if p1 and p2 and p1 != p2:
            self.add_error('new_password2', 'Passwords do not match.')
        return cleaned
