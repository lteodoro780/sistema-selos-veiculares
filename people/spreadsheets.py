"""Planilha de atualização: identificador assinado e células explicitamente textuais."""
import csv
import io
import zipfile
from xml.sax.saxutils import escape

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .forms import EDIT_FIELDS, PersonForm
from .models import Person, PersonChange, CompletionImport

SALT = 'people.completion.v1'
HEADERS = ('id_pessoa', 'chave', *EDIT_FIELDS, 'pendencias')


def snapshot(person):
    return {field: getattr(person, field) or '' for field in EDIT_FIELDS}


def make_token(person):
    return signing.dumps({'id': person.pk, 'uid': str(person.public_id), 'values': snapshot(person)}, salt=SALT, compress=True)


def column_name(index):
    result = ''
    while index:
        index, digit = divmod(index - 1, 26)
        result = chr(65 + digit) + result
    return result


def xlsx_bytes(rows):
    """XLSX OOXML mínimo, sem fórmulas, mantendo zeros em CPF, telefone e ramal."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>''')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Pendências" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', '''<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF174F2A"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''')
        xml_rows = []
        for index, row in enumerate(rows, 1):
            cells = []
            for col, value in enumerate(row, 1):
                value = ''.join(ch for ch in str(value or '') if ord(ch) >= 32 or ch in '\n\r\t')
                cells.append(f'<c r="{column_name(col)}{index}" t="inlineStr" s="{1 if index == 1 else 0}"><is><t xml:space="preserve">{escape(value)}</t></is></c>')
            xml_rows.append(f'<row r="{index}">{"".join(cells)}</row>')
        end = f'{column_name(len(HEADERS))}{len(xml_rows)}'
        archive.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane xSplit="2" ySplit="1" topLeftCell="C2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="12" customWidth="1"/><col min="2" max="2" width="12" hidden="1" customWidth="1"/><col min="3" max="16" width="24" customWidth="1"/></cols><sheetData>{"".join(xml_rows)}</sheetData><autoFilter ref="A1:{end}"/></worksheet>')
    return buffer.getvalue()


def export_people(people):
    rows = [HEADERS]
    for person in people:
        rows.append((str(person.pk), make_token(person), *snapshot(person).values(), ', '.join(label for _, label in person.missing_fields)))
    return xlsx_bytes(rows)


def read_rows(content, filename):
    from accounts.csv_import import _decode_file, _xlsx_rows
    if filename.lower().endswith('.xlsx'):
        sheets = _xlsx_rows(content)
        matching = [rows for _, rows in sheets if rows and 'id_pessoa' in rows[0]]
        if len(matching) != 1:
            raise ValueError('Use a planilha de pendências exportada pelo sistema, com uma única aba de dados.')
        rows = matching[0]
    else:
        text = _decode_file(content)
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=';,\t')
        except csv.Error:
            raise ValueError('Não foi possível reconhecer as colunas do CSV.')
        rows = list(csv.reader(io.StringIO(text), dialect=dialect))
    if not rows:
        raise ValueError('Planilha vazia.')
    headers = [value.strip() for value in rows[0]]
    if len(headers) != len(set(headers)) or not {'id_pessoa', 'chave'}.issubset(headers):
        raise ValueError('As colunas id_pessoa e chave precisam ser preservadas e não podem se repetir.')
    if any(value not in HEADERS for value in headers):
        raise ValueError('A planilha contém colunas desconhecidas. Preserve os nomes do arquivo exportado.')
    return [(index, dict(zip(headers, values))) for index, values in enumerate(rows[1:], 2) if any(values)]


def preview_upload(content, filename, replace_existing=False):
    records = read_rows(content, filename)
    if len(records) > 5000:
        raise ValueError('Limite de 5.000 pessoas por importação.')
    payload, errors, seen, skipped = [], [], set(), 0
    for line, row in records:
        try:
            identity = signing.loads(row.get('chave', ''), salt=SALT)
            pk = int(row.get('id_pessoa', ''))
            if pk != identity['id'] or pk in seen:
                raise ValueError('Identificador alterado ou repetido.')
            seen.add(pk)
            person = Person.objects.get(pk=pk, public_id=identity['uid'])
            current = snapshot(person)
            data = dict(current, is_active=person.is_active, review_status=Person.Review.PENDING, source='Edição administrativa')
            requested = []
            for field in EDIT_FIELDS:
                value = row.get(field, '').strip()
                if not value or value == str(identity['values'].get(field) or '') or value == str(current[field]):
                    continue
                if current[field] and not (field == 'classe_funcional' and current[field] == 'SEM_CLASSE') and not replace_existing:
                    skipped += 1
                    continue
                if str(current[field]) != str(identity['values'].get(field) or ''):
                    raise ValueError('Cadastro alterado após a exportação. Exporte novamente para evitar sobrescrever uma correção.')
                data[field] = value
                requested.append(field)
            form = PersonForm(data, instance=person)
            if not form.is_valid():
                detail = '; '.join(f'{field}: {", ".join(values)}' for field, values in form.errors.items())
                raise ValueError(detail)
            changes = {field: {'before': current[field], 'after': form.cleaned_data[field] or ''} for field in requested if current[field] != (form.cleaned_data[field] or '')}
            if changes:
                payload.append({'id': pk, 'uid': str(person.public_id), 'name': person.nome_exibicao, 'changes': changes})
        except (signing.BadSignature, Person.DoesNotExist, KeyError, TypeError, ValueError) as exc:
            errors.append(f'Linha {line}: {str(exc) if not isinstance(exc, signing.BadSignature) else "Chave inválida; utilize a planilha exportada pelo sistema."}')
    if errors:
        raise ValueError('\n'.join(errors[:50]))
    return payload, skipped


@transaction.atomic
def apply_completion(batch_id, actor):
    batch = CompletionImport.objects.select_for_update().get(pk=batch_id, actor=actor)
    if batch.applied_at:
        raise ValueError('Esta importação já foi confirmada.')
    if timezone.now() - batch.created_at > timezone.timedelta(hours=24):
        raise ValueError('A prévia expirou. Envie a planilha novamente.')
    prepared = []
    for item in batch.payload:
        person = Person.objects.select_for_update().get(pk=item['id'], public_id=item['uid'])
        for field, change in item['changes'].items():
            if (getattr(person, field) or '') != change['before']:
                raise ValueError(f'{person.nome_exibicao}: o cadastro mudou depois da prévia. Valide a planilha novamente.')
            setattr(person, field, change['after'] or (None if field == 'cpf' else ''))
        person.review_status = Person.Review.PENDING
        person.reviewed_at = None
        person.reviewed_by = None
        person.full_clean(exclude=['legacy_user'])
        prepared.append((person, item))
    for person, item in prepared:
        person.save()
        PersonChange.objects.create(person=person, actor=actor, source=f'Planilha: {batch.filename}'[:200], changes=item['changes'])
    batch.applied_at = timezone.now()
    batch.save(update_fields=['applied_at'])
    return len(prepared)
