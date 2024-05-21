from django import forms
from django.core.validators import MinLengthValidator

class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput, validators=[MinLengthValidator(8)])

class UploadFileForm(forms.Form):
    file = forms.FileField()