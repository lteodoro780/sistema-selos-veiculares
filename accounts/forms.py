import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Usuário")
    password = forms.CharField(label="Senha", strip=False, widget=forms.PasswordInput)


class RegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "cpf", "password1", "password2")

    def clean_cpf(self):
        value = re.sub(r"\D", "", self.cleaned_data.get("cpf") or "")
        return value or None


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "first_name", "last_name", "email", "cpf", "telefone", "ramal", "vinculo",
            "classe_funcional", "cargo", "nome_preferido", "identidade_funcional",
            "organizacao", "secao",
        )

    def clean_cpf(self):
        value = re.sub(r"\D", "", self.cleaned_data.get("cpf") or "")
        return value or None


class CSVImportForm(forms.Form):
    arquivo = forms.FileField(
        label="Planilha de importação",
        help_text="Arquivo Excel (.xlsx), CSV ou TSV de até 5 MB.",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx,.csv,.tsv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,text/tab-separated-values"}),
    )

    def clean_arquivo(self):
        upload = self.cleaned_data["arquivo"]
        if upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError("O arquivo não pode ultrapassar 5 MB.")
        if not upload.name.lower().endswith((".xlsx", ".csv", ".tsv")):
            raise forms.ValidationError("Selecione um arquivo com extensão .xlsx, .csv ou .tsv.")
        return upload
