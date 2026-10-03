from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from xml.etree.ElementTree import ParseError

from accounts.access import operator_required
from .forms import EDIT_FIELDS, PersonForm, CompletionUploadForm
from .models import Person, PersonChange, CompletionImport
from .spreadsheets import apply_completion, export_people, preview_upload, snapshot


def directory(request, incomplete=False):
    qs = Person.objects.annotate(vehicle_count=Count('veiculos', distinct=True)).order_by('nome_preferido', 'first_name', 'pk')
    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(nome_preferido__icontains=query) | Q(telefone__icontains=query) | Q(ramal__icontains=query) | Q(secao__icontains=query) | Q(veiculos__placa__icontains=query)).distinct()
    category = request.GET.get('categoria', '')
    if category in dict(Person.Classe.choices):
        qs = qs.filter(classe_funcional=category)
    state = request.GET.get('situacao', '')
    pending = request.GET.get('pendencia', '')
    # Completeness depends on alternative identifiers/contact and on colaboradory status.
    rows = list(qs)
    if incomplete:
        rows = [p for p in rows if p.missing_fields]
    if pending:
        rows = [p for p in rows if pending in {key for key, _ in p.missing_fields}]
    if state == 'incompleto':
        rows = [p for p in rows if p.missing_fields]
    elif state == 'aguardando':
        rows = [p for p in rows if not p.missing_fields and p.review_status == Person.Review.PENDING]
    elif state == 'conferido':
        rows = [p for p in rows if not p.missing_fields and p.review_status == Person.Review.VERIFIED]
    return rows


@operator_required
def person_list(request, incomplete=False):
    rows = directory(request, incomplete)
    all_people = list(Person.objects.all())
    params = request.GET.copy()
    params.pop('page', None)
    context = {
        'page': Paginator(rows, 25).get_page(request.GET.get('page')), 'incomplete': incomplete,
        'classes': Person.Classe.choices, 'params': params.urlencode(),
        'total': len(all_people), 'missing_count': sum(bool(p.missing_fields) for p in all_people),
        'awaiting_count': sum(not p.missing_fields and p.review_status == Person.Review.PENDING for p in all_people),
        'verified_count': sum(not p.missing_fields and p.review_status == Person.Review.VERIFIED for p in all_people),
    }
    return render(request, 'people/list.html', context)


@operator_required
def person_edit(request, pk=None):
    person = get_object_or_404(Person, pk=pk) if pk else Person()
    before = snapshot(person)
    before.update(is_active=person.is_active, review_status=person.review_status)
    form = PersonForm(request.POST or None, instance=person, initial={'version': person.updated_at.isoformat() if person.pk else '', 'source': 'Edição administrativa'})
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                if pk:
                    current = Person.objects.select_for_update().get(pk=pk)
                    if request.POST.get('version') != current.updated_at.isoformat():
                        raise ValueError('O cadastro mudou enquanto você editava. Reabra a ficha para conferir os dados atuais.')
                changed = {field: {'before': before.get(field), 'after': form.cleaned_data.get(field)} for field in (*EDIT_FIELDS, 'is_active', 'review_status') if before.get(field) != form.cleaned_data.get(field)}
                person = form.save(commit=False)
                if person.review_status == Person.Review.VERIFIED:
                    person.reviewed_by, person.reviewed_at = request.user, timezone.now()
                else:
                    person.reviewed_by, person.reviewed_at = None, None
                person.save()
                if changed or not pk:
                    PersonChange.objects.create(person=person, actor=request.user, source=form.cleaned_data['source'], changes=changed)
            messages.success(request, 'Cadastro salvo. A pessoa não possui conta de acesso.')
            return redirect('people:detail', pk=person.pk)
        except (ValueError, IntegrityError) as exc:
            form.add_error(None, str(exc) if isinstance(exc, ValueError) else 'CPF ou referência já utilizado em outro cadastro.')
    return render(request, 'people/form.html', {'form': form, 'person': person})


@operator_required
def person_detail(request, pk):
    from operations.views import user_detail
    return user_detail(request, pk)


@operator_required
@require_POST
def quick_edit(request, pk):
    with transaction.atomic():
        person = get_object_or_404(Person.objects.select_for_update(), pk=pk)
        before = snapshot(person)
        data = dict(before, is_active=person.is_active, review_status=Person.Review.PENDING, source='Edição administrativa')
        for field in ('telefone', 'ramal', 'cargo', 'secao', 'identidade_funcional'):
            data[field] = request.POST.get(field, '')
        form = PersonForm(data, instance=person)
        if request.POST.get('version') != person.updated_at.isoformat():
            messages.error(request, 'O cadastro mudou. Confira os dados e tente novamente.')
        elif form.is_valid():
            changes = {field: {'before': before[field], 'after': form.cleaned_data[field] or ''} for field in EDIT_FIELDS if before[field] != (form.cleaned_data[field] or '')}
            if changes:
                person = form.save(commit=False)
                person.reviewed_by = person.reviewed_at = None
                person.save()
                PersonChange.objects.create(person=person, actor=request.user, source='Edição rápida', changes=changes)
            messages.success(request, 'Cadastro atualizado.')
        else:
            detail = '; '.join(f'{field}: {", ".join(errors)}' for field, errors in form.errors.items())
            messages.error(request, f'Confira os dados: {detail}')
    destination = request.POST.get('return', '')
    if url_has_allowed_host_and_scheme(destination, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(destination)
    return redirect('people:incomplete')


@operator_required
def export_pending(request):
    rows = directory(request, incomplete=True)
    response = HttpResponse(export_people(rows), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="pendencias-pessoas.xlsx"'
    response['Cache-Control'] = 'no-store'
    return response


@operator_required
def import_pending(request):
    form = CompletionUploadForm(request.POST or None, request.FILES or None)
    batch = None
    skipped = 0
    if request.method == 'POST':
        action = request.POST.get('action', 'preview')
        if action == 'confirm':
            batch = get_object_or_404(CompletionImport, pk=request.POST.get('batch'), actor=request.user)
            try:
                count = apply_completion(batch.pk, request.user)
                messages.success(request, f'{count} cadastro(s) atualizado(s). Confira as fichas antes de marcar como conferidas.')
                return redirect('people:incomplete')
            except (ValueError, IntegrityError, ValidationError) as exc:
                messages.error(request, str(exc) if not isinstance(exc, IntegrityError) else 'A atualização foi cancelada: há dados duplicados. Nenhum cadastro foi alterado.')
                batch = None
        elif form.is_valid():
            upload = form.cleaned_data['arquivo']
            try:
                payload, skipped = preview_upload(upload.read(), upload.name, form.cleaned_data['replace_existing'])
                if payload:
                    batch = CompletionImport.objects.create(actor=request.user, filename=upload.name[:200], payload=payload, replace_existing=form.cleaned_data['replace_existing'])
                else:
                    messages.info(request, 'Nenhuma mudança para aplicar. Campos vazios no arquivo não apagam os dados atuais.')
            except (ValueError, ValidationError, ParseError) as exc:
                form.add_error('arquivo', str(exc))
    changes = []
    if batch:
        for item in batch.payload:
            for field, values in item['changes'].items():
                changes.append(dict(person=item['name'], id=item['id'], field=Person._meta.get_field(field).verbose_name, **values))
    return render(request, 'people/import.html', {'form': form, 'batch': batch, 'changes': changes, 'skipped': skipped})
