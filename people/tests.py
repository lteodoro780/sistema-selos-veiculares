import csv
import io
from datetime import timedelta

from django.contrib.auth import authenticate
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from accounts.models import User
from accounts.csv_import import _xlsx_rows
from .forms import EDIT_FIELDS
from .models import Person, PersonChange, CompletionImport
from .spreadsheets import HEADERS, export_people, snapshot, make_token, preview_upload, apply_completion, xlsx_bytes


class AdministrativePeopleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='TestPassword!', role='ADMINISTRADOR', is_staff=True)
        self.person = Person.objects.create(first_name='Ana', nome_preferido='ANA', cargo='COLABORADOR', secao='Alfa')
        self.client.force_login(self.admin, backend='accounts.backends.AdminModelBackend')

    def file(self, changes, person=None):
        person = person or self.person
        values = dict(id_pessoa=str(person.pk), chave=make_token(person), **snapshot(person), pendencias='')
        values.update(changes)
        out = io.StringIO()
        writer = csv.DictWriter(out, HEADERS, delimiter=';')
        writer.writeheader()
        writer.writerow(values)
        return out.getvalue().encode('utf-8')

    def test_person_is_not_an_authentication_account(self):
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(hasattr(self.person, 'password'))
        self.assertIsNone(authenticate(username=self.person.username, password='anything'))

    def test_non_admin_cannot_authenticate_or_use_saved_session(self):
        user = User.objects.create_user('visitor', password='TestPassword!', is_staff=True)
        self.assertIsNone(authenticate(username='visitor', password='TestPassword!'))
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')
        for route in ['people:list', 'people:export', 'operations:dashboard', 'accounts:csv-import', 'admin:index']:
            self.assertEqual(self.client.get(reverse(route)).status_code, 302)

    def test_anonymous_cannot_read_people_or_media(self):
        self.client.logout()
        for path in ['/pessoas/', '/pessoas/pendencias/exportar/', '/cadastro/', '/media/documentos/private.pdf']:
            self.assertEqual(self.client.get(path).status_code, 302)

    def test_page_search_filters_and_edit_link(self):
        response = self.client.get(reverse('people:incomplete'), {'q': 'Ana', 'pendencia': 'contato'})
        self.assertContains(response, 'ANA')
        self.assertContains(response, reverse('people:edit', args=[self.person.pk]))
        response = self.client.get(reverse('people:list'), {'q': 'nonexistent'})
        self.assertContains(response, 'Nenhum cadastro corresponde')

    def test_export_xlsx_preserves_ids_and_leading_zeroes_as_text(self):
        self.person.ramal = '0012'
        self.person.save()
        content = export_people([self.person])
        rows = _xlsx_rows(content)[0][1]
        self.assertEqual(rows[0], list(HEADERS))
        values = dict(zip(rows[0], rows[1]))
        self.assertEqual(values['ramal'], '0012')
        self.assertEqual(signing.loads(values['chave'], salt='people.completion.v1')['id'], self.person.pk)
        changes, skipped = preview_upload(content, 'test.xlsx')
        self.assertEqual(changes, [])

    def test_roundtrip_updates_empty_fields_only_and_logs_actor(self):
        original_accounts = User.objects.count()
        payload, skipped = preview_upload(self.file({'telefone': '00000000001', 'secao': 'Beta'}), 'file.csv')
        self.assertEqual(skipped, 1)
        self.assertNotIn('secao', payload[0]['changes'])
        batch = CompletionImport.objects.create(actor=self.admin, filename='file.csv', payload=payload)
        self.assertEqual(apply_completion(batch.pk, self.admin), 1)
        self.person.refresh_from_db()
        self.assertEqual(self.person.telefone, '(00) 00000-0001')
        self.assertEqual(self.person.secao, 'Alfa')
        self.assertEqual(User.objects.count(), original_accounts)
        self.assertEqual(PersonChange.objects.get().actor, self.admin)
        with self.assertRaises(ValueError):
            apply_completion(batch.pk, self.admin)

    def test_replace_requires_explicit_option_and_blanks_never_clear(self):
        data = self.file({'secao': 'Beta', 'first_name': ''})
        payload, _ = preview_upload(data, 'file.csv', replace_existing=True)
        self.assertEqual(payload[0]['changes']['secao'], {'before': 'Alfa', 'after': 'Beta'})
        self.assertNotIn('first_name', payload[0]['changes'])

    def test_modified_identifier_or_invalid_cpf_rejected(self):
        for changes in ({'id_pessoa': '999'}, {'cpf': '123'}, {'chave': 'invalid'}, {'telefone': '1234'}):
            with self.assertRaises(ValueError):
                preview_upload(self.file(changes), 'file.csv')

    def test_preview_does_not_write_people_and_batch_belongs_to_actor(self):
        upload = SimpleUploadedFile('pending.csv', self.file({'ramal': '0012'}))
        response = self.client.post(reverse('people:import'), {'arquivo': upload, 'action': 'preview'})
        self.assertContains(response, 'Confirmar e salvar alterações')
        self.person.refresh_from_db()
        self.assertEqual(self.person.ramal, '')
        self.assertEqual(PersonChange.objects.count(), 0)
        batch = CompletionImport.objects.get()
        other = User.objects.create_user('other', role='ADMINISTRADOR')
        self.client.force_login(other, backend='accounts.backends.AdminModelBackend')
        self.assertEqual(self.client.post(reverse('people:import'), {'action': 'confirm', 'batch': batch.pk}).status_code, 404)

    def test_conflict_after_preview_rolls_back_entire_batch(self):
        second = Person.objects.create(first_name='João')
        rows1, _ = preview_upload(self.file({'telefone': '00000000001'}), 'file.csv')
        rows2, _ = preview_upload(self.file({'ramal': '0020'}, second), 'file.csv')
        batch = CompletionImport.objects.create(actor=self.admin, filename='file.csv', payload=rows1 + rows2)
        second.ramal = '0030'
        second.save()
        with self.assertRaises(ValueError):
            apply_completion(batch.pk, self.admin)
        self.person.refresh_from_db()
        self.assertEqual(self.person.telefone, '')
        self.assertEqual(PersonChange.objects.count(), 0)

    def test_changed_since_export_is_not_overwritten(self):
        data = self.file({'secao': 'Beta'})
        self.person.secao = 'Gama'
        self.person.save()
        with self.assertRaises(ValueError):
            preview_upload(data, 'file.csv', replace_existing=True)

    def test_manual_save_preserves_vehicle_links_and_records_review(self):
        from vehicles.models import Vehicle
        vehicle = Vehicle.objects.create(proprietario=self.person, placa='ABC1D23', renavam='00000000001', marca='Teste', modelo='Teste', cor='Prata', ano_fabricacao=2025, ano_modelo=2025)
        data = dict(snapshot(self.person), telefone='00000000001', identidade_funcional='001234', is_active='on', review_status='VERIFIED', source='Documento', version=self.person.updated_at.isoformat())
        response = self.client.post(reverse('people:edit', args=[self.person.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.proprietario_id, self.person.pk)
        self.assertEqual(self.person.completion_status, 'Conferido')
        self.assertEqual(self.person.reviewed_by, self.admin)
        self.assertEqual(PersonChange.objects.get().source, 'Documento')

    def test_cannot_verify_missing_fields_or_save_stale_form(self):
        data = dict(snapshot(self.person), review_status='VERIFIED', source='Documento', version=self.person.updated_at.isoformat())
        response = self.client.post(reverse('people:edit', args=[self.person.pk]), data)
        self.assertContains(response, 'Preencha as pendências')
        data.update(review_status='PENDING', version='old', ramal='1234')
        response = self.client.post(reverse('people:edit', args=[self.person.pk]), data)
        self.assertContains(response, 'cadastro mudou')

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin, backend='accounts.backends.AdminModelBackend')
        self.assertEqual(client.post(reverse('people:import'), {'action': 'confirm'}).status_code, 403)

    def test_inline_contact_edit_is_audited_without_access_account(self):
        data = dict(snapshot(self.person), ramal='0020', version=self.person.updated_at.isoformat(), **{'return': '/pessoas/incompletos/'})
        response = self.client.post(reverse('people:quick', args=[self.person.pk]), data)
        self.assertRedirects(response, '/pessoas/incompletos/')
        self.person.refresh_from_db()
        self.assertEqual(self.person.ramal, '0020')
        self.assertEqual(PersonChange.objects.get().source, 'Edição rápida')
        self.assertEqual(User.objects.count(), 1)

    def test_all_administrative_pages_render(self):
        routes = ['people:list', 'people:incomplete', 'people:create', 'people:import', 'operations:dashboard', 'vehicles:list', 'documents:list', 'seals:list', 'accounts:csv-import']
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)
        self.assertEqual(self.client.get(reverse('people:detail', args=[self.person.pk])).status_code, 200)
