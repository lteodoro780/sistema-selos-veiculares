import csv
from datetime import date

from django import forms
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from accounts.access import operator_required
from people.models import Person
from vehicles.models import Vehicle
from documents.models import DriverDocument, VehicleDocument
from seals.models import Seal
from seals.validation import seal_validation
from operations.models import Occurrence

AREAS = [('pessoas', 'Pessoas'), ('veiculos', 'Veículos'), ('documentos', 'Documentos'), ('selos', 'Selos'), ('ocorrencias', 'Ocorrências')]


class ReportFilters(forms.Form):
    area = forms.ChoiceField(choices=AREAS, initial='pessoas', label='Relatório')
    q = forms.CharField(required=False, max_length=150, label='Nome, placa ou código')
    inicio = forms.DateField(required=False, label='De', widget=forms.DateInput(attrs={'type': 'date'}))
    fim = forms.DateField(required=False, label='Até', widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        data = super().clean()
        if data.get('inicio') and data.get('fim') and data['inicio'] > data['fim']:
            raise forms.ValidationError('A data inicial deve ser anterior ou igual à data final.')
        return data


def dates(qs, field, filters):
    if filters.get('inicio'):
        qs = qs.filter(**{f'{field}__date__gte': filters['inicio']})
    if filters.get('fim'):
        qs = qs.filter(**{f'{field}__date__lte': filters['fim']})
    return qs


def owner_search(prefix, query):
    return Q(**{prefix + 'first_name__icontains': query}) | Q(**{prefix + 'last_name__icontains': query}) | Q(**{prefix + 'nome_preferido__icontains': query})


def report_rows(filters):
    area, q = filters['area'], filters.get('q', '')
    if area == 'pessoas':
        qs = Person.objects.all()
        if q:
            qs = qs.filter(owner_search('', q) | Q(cargo__icontains=q) | Q(secao__icontains=q))
        qs = dates(qs, 'created_at', filters).order_by('nome_preferido', 'first_name', 'pk')
        return ['Pessoa', 'Cargo', 'Seção', 'Telefone', 'Ramal', 'Situação', 'Conferência'], [
            [obj.nome_exibicao, obj.identificacao_funcional, obj.secao, obj.telefone, obj.ramal,
             'Ativo' if obj.is_active else 'Inativo', obj.completion_status] for obj in qs]
    if area == 'veiculos':
        qs = Vehicle.objects.select_related('proprietario')
        if q:
            qs = qs.filter(owner_search('proprietario__', q) | Q(placa__icontains=q) | Q(modelo__icontains=q))
        qs = dates(qs, 'criado_em', filters).order_by('placa')
        return ['Placa', 'Proprietário', 'Tipo', 'Marca / modelo', 'Cor', 'Situação'], [
            [obj.placa, str(obj.proprietario), obj.get_tipo_display(), f'{obj.marca} {obj.modelo}', obj.cor, obj.get_status_display()] for obj in qs]
    if area == 'documentos':
        cnhs = DriverDocument.objects.select_related('usuario')
        crlvs = VehicleDocument.objects.select_related('veiculo__proprietario')
        if q:
            cnhs = cnhs.filter(owner_search('usuario__', q) | Q(numero__icontains=q))
            crlvs = crlvs.filter(owner_search('veiculo__proprietario__', q) | Q(veiculo__placa__icontains=q))
        cnhs, crlvs = dates(cnhs, 'criado_em', filters), dates(crlvs, 'criado_em', filters)
        return ['Documento', 'Proprietário', 'Placa', 'Identificação', 'Validade / exercício', 'Situação'], (
            [['CNH', str(obj.usuario), '', obj.numero, obj.validade, obj.get_status_display()] for obj in cnhs]
            + [['CRLV', str(obj.veiculo.proprietario), obj.veiculo.placa, '', str(obj.exercicio), obj.get_status_display()] for obj in crlvs])
    if area == 'selos':
        qs = Seal.objects.select_related('veiculo__proprietario', 'emitido_por')
        if q:
            qs = qs.filter(owner_search('veiculo__proprietario__', q) | Q(numero_serial__icontains=q) | Q(veiculo__placa__icontains=q))
        qs = dates(qs, 'emitido_em', filters).order_by('-emitido_em')
        labels = {'valid': 'Válido', 'invalid': 'Inválido', 'attention': 'Exige conferência'}
        return ['Código', 'Proprietário', 'Placa', 'Situação registrada', 'Validade', 'Consulta atual', 'Emitido por'], [
            [obj.numero_serial, str(obj.veiculo.proprietario), obj.veiculo.placa, obj.get_status_display(), obj.validade,
             labels[seal_validation(obj)['state']], obj.emitido_por.username if obj.emitido_por else ''] for obj in qs]
    qs = Occurrence.objects.select_related('proprietario', 'veiculo', 'registrado_por')
    if q:
        qs = qs.filter(owner_search('proprietario__', q) | Q(numero__icontains=q) | Q(veiculo__placa__icontains=q) | Q(local__icontains=q))
    qs = dates(qs, 'data_hora', filters).order_by('-data_hora')
    return ['Número', 'Data e hora', 'Proprietário', 'Placa', 'Tipo', 'Situação', 'Local', 'Registrado por'], [
        [obj.numero, timezone.localtime(obj.data_hora).strftime('%d/%m/%Y %H:%M'), str(obj.proprietario), obj.veiculo.placa,
         obj.get_tipo_display(), obj.get_status_display(), obj.local, obj.registrado_por.username] for obj in qs]


def filters_for(request):
    params = request.GET.copy()
    params.setdefault('area', 'pessoas')
    return ReportFilters(params)


@never_cache
@operator_required
def report(request):
    form = filters_for(request)
    valid = form.is_valid()
    headers, rows = report_rows(form.cleaned_data) if valid else ([], [])
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'reports/index.html', {
        'form': form, 'headers': headers, 'page': Paginator(rows, 50).get_page(request.GET.get('page')),
        'params': params.urlencode(), 'valid': valid, 'total': len(rows), 'areas': AREAS,
        'people_count': Person.objects.count(), 'vehicle_count': Vehicle.objects.count(),
        'document_count': DriverDocument.objects.count() + VehicleDocument.objects.count(), 'seal_count': Seal.objects.count(),
    }, status=200 if valid else 400)


def safe_cell(value):
    if value is None:
        return ''
    value = value.strftime('%d/%m/%Y') if isinstance(value, date) else str(value)
    # Protect Excel exports even when a formula starts after whitespace/control chars.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value


@never_cache
@operator_required
def export_csv(request):
    form = filters_for(request)
    if not form.is_valid():
        return HttpResponse('Filtros inválidos. Confira o período e o relatório.', status=400)
    headers, rows = report_rows(form.cleaned_data)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="relatorio-{form.cleaned_data["area"]}.csv"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_cell(value) for value in row])
    return response
