from datetime import timedelta
from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import authenticate
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from people.models import Person, PersonChange
from vehicles.models import Vehicle
from documents.models import DriverDocument
from seals.models import Seal
from operations.models import Occurrence


class OperatorFixture:
    @classmethod
    def setUpTestData(cls):
        cls.administrator = User.objects.create_superuser('admin', password='PortalSenha@4567', role='ADMINISTRADOR')
        cls.patrol = User.objects.create_user('patrulha', password='PortalSenha@4567', role='PATRULHANTE')
        cls.person = Person.objects.create(username='pessoa', first_name='Pessoa', nome_preferido='PESSOA', cargo='COLABORADOR')
        cls.other = Person.objects.create(username='outra', first_name='Outra pessoa')
        cls.vehicle = Vehicle.objects.create(proprietario=cls.person, placa='ABC1D23', renavam='00000000123', marca='Marca', modelo='Modelo', cor='Verde', ano_fabricacao=2025, ano_modelo=2025, status='APROVADO')

    def setUp(self):
        self.client.force_login(self.patrol)


class OperatorPortalTests(OperatorFixture, TestCase):
    def test_both_roles_use_same_portal_and_login(self):
        routes = ['accounts:dashboard', 'people:list', 'people:create', 'people:incomplete', 'accounts:profile',
                  'accounts:csv-import', 'people:import', 'vehicles:list', 'vehicles:create', 'documents:list',
                  'documents:cnh-create', 'documents:crlv-create', 'seals:list', 'seals:mobile',
                  'operations:dashboard', 'operations:occurrence-list', 'operations:occurrence-create',
                  'operations:link-seal', 'reports:index']
        for user in (self.administrator, self.patrol):
            self.assertIsNotNone(authenticate(username=user.username, password='PortalSenha@4567'))
            self.client.force_login(user)
            for route in routes:
                with self.subTest(user=user.role, route=route):
                    self.assertEqual(self.client.get(reverse(route)).status_code, 200)
            page = self.client.get(reverse('people:list'))
            for route in ('operations:link-seal', 'reports:index', 'accounts:csv-import', 'seals:mobile'):
                self.assertContains(page, reverse(route))
            if user == self.patrol:
                self.assertNotContains(page, 'href="/admin/"')
            else:
                self.assertContains(page, 'href="/admin/"')

    def test_patrol_denied_admin_even_if_staff_flag_is_set(self):
        self.patrol.is_staff = True
        self.patrol.save(update_fields=['is_staff'])
        for path in ('/admin/', '/admin/login/', '/admin/accounts/user/', '/admin/accounts/user/add/', '/admin/auth/group/add/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)
                self.assertEqual(self.client.post(path, {'role':'ADMINISTRADOR','is_superuser':'on'}).status_code, 403)
        self.patrol.refresh_from_db()
        self.assertFalse(self.patrol.is_superuser)
        self.assertEqual(self.patrol.role, 'PATRULHANTE')

    def test_inactive_and_unapproved_roles_cannot_login(self):
        for role in ('USUARIO', 'SUPERVISOR', 'ADMINISTRADOR', 'PATRULHANTE'):
            user = User.objects.create_user(role, password='PortalSenha@4567', role=role, is_active=role in {'USUARIO','SUPERVISOR'}, is_staff=True)
            self.assertIsNone(authenticate(username=user.username, password='PortalSenha@4567'))
        self.patrol.is_active = False
        self.patrol.save()
        self.assertEqual(self.client.get('/pessoas/').status_code, 302)

    def test_profile_post_cannot_promote_patrol(self):
        response = self.client.post(reverse('accounts:profile'), {'first_name':'Operador', 'vinculo':'COLABORADOR', 'classe_funcional':'GRUPO_B', 'role':'ADMINISTRADOR', 'is_staff':'on', 'is_superuser':'on'})
        self.assertEqual(response.status_code, 302)
        self.patrol.refresh_from_db()
        self.assertFalse(self.patrol.is_staff or self.patrol.is_superuser)
        self.assertEqual(self.patrol.role, 'PATRULHANTE')

    def test_patrol_creates_person_without_creating_account_and_records_actor(self):
        response = self.client.post(reverse('people:create'), {'first_name':'Pessoa Nova', 'nome_preferido':'NOVA', 'vinculo':'COLABORADOR', 'classe_funcional':'GRUPO_B', 'review_status':'PENDING', 'source':'Edição administrativa', 'is_active':'on', 'role':'ADMINISTRADOR'})
        self.assertEqual(response.status_code, 302)
        person = Person.objects.get(nome_preferido='NOVA')
        self.assertEqual(PersonChange.objects.get(person=person).actor, self.patrol)
        self.assertEqual(User.objects.count(), 2)

    def test_patrol_imports_people_not_access_accounts(self):
        blob = b'username;first_name;role\nimportado;Pessoa importada;PATRULHANTE\n'
        response = self.client.post(reverse('accounts:csv-import'), {'action':'preview', 'arquivo':SimpleUploadedFile('pessoas.csv', blob)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirmar importação')
        self.assertEqual(self.client.post(reverse('accounts:csv-import'), {'action':'confirm'}).status_code, 302)
        self.assertTrue(Person.objects.filter(first_name='Pessoa importada').exists())
        self.assertEqual(User.objects.count(), 2)

    def test_patrol_creates_and_edits_vehicle(self):
        data = {'proprietario':self.person.pk, 'placa':'DEF4G56', 'renavam':'00000000456', 'tipo':'MOTO', 'marca':'Marca', 'modelo':'Moto', 'cor':'Preta', 'ano_fabricacao':2025, 'ano_modelo':2025, 'status':'EM_ANALISE'}
        self.assertEqual(self.client.post(reverse('vehicles:create'), data).status_code, 302)
        vehicle = Vehicle.objects.get(placa='DEF4G56')
        data.update(cor='Azul', status='APROVADO')
        self.assertEqual(self.client.post(reverse('vehicles:edit', args=[vehicle.pk]), data).status_code, 302)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.cor, 'Azul')
        self.assertEqual(vehicle.status, 'APROVADO')

    def test_patrol_uploads_edits_and_downloads_document(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            data = {'usuario':self.person.pk, 'numero':'QA123', 'categoria':'B', 'validade':'2030-12-31', 'status':'PENDENTE', 'arquivo':SimpleUploadedFile('teste.pdf', b'%PDF-1.4 QA')}
            self.assertEqual(self.client.post(reverse('documents:cnh-create'), data).status_code, 302)
            document = DriverDocument.objects.get(numero='QA123')
            data.pop('arquivo')
            data.update(status='VERIFICADO')
            self.assertEqual(self.client.post(reverse('documents:cnh-edit', args=[document.pk]), data).status_code, 302)
            document.refresh_from_db()
            self.assertEqual(document.status, 'VERIFICADO')
            response = self.client.get(document.arquivo.url)
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_patrol_creates_occurrence_with_actor(self):
        data = {'proprietario':self.person.pk, 'veiculo':self.vehicle.pk, 'tipo':'ABORDAGEM', 'status':'ABERTA', 'data_hora':'2026-09-28T10:00', 'local':'Local de QA', 'descricao':'Descrição de QA'}
        self.assertEqual(self.client.post(reverse('operations:occurrence-create'), data).status_code, 302)
        self.assertEqual(Occurrence.objects.get().registrado_por, self.patrol)

    def test_create_patrol_command_has_no_admin_privileges(self):
        with patch('builtins.input', return_value='patrulha2'), patch('accounts.management.commands.criar_administrador.getpass', return_value='SenhaPrivada@234567'):
            call_command('criar_patrulhante', stdout=StringIO())
        user = User.objects.get(username='patrulha2')
        self.assertEqual(user.role, 'PATRULHANTE')
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertTrue(user.check_password('SenhaPrivada@234567'))

    def test_django_admin_preserves_patrol_role_and_removes_privileged_flags(self):
        self.client.force_login(self.administrator)
        response = self.client.get('/admin/accounts/user/')
        self.assertContains(response, 'patrulha')
        model_admin = admin.site._registry[User]
        self.patrol.is_superuser = True
        model_admin.save_model(None, self.patrol, None, True)
        self.patrol.refresh_from_db()
        self.assertEqual(self.patrol.role, 'PATRULHANTE')
        self.assertFalse(self.patrol.is_staff or self.patrol.is_superuser)


class SealLinkAndReportTests(OperatorFixture, TestCase):
    def link_data(self, **changes):
        data = {'codigo_selo':'S-1234', 'proprietario':self.person.pk, 'veiculo':self.vehicle.pk,
                'validade':(timezone.localdate()+timedelta(days=30)).isoformat()}
        data.update(changes)
        return {'modo': 'vincular', **{f'existente-{key}': value for key, value in data.items()}}

    def test_link_generates_qr_and_records_patrol_with_explicit_activation(self):
        response = self.client.post(reverse('operations:link-seal'), self.link_data(ativar_apos_vinculo='on'))
        self.assertEqual(response.status_code, 302)
        seal = Seal.objects.get(numero_serial='S-1234')
        self.assertEqual(seal.emitido_por, self.patrol)
        self.assertEqual(seal.status, 'ATIVO')
        self.assertEqual(self.client.get(reverse('seals:qr', args=[seal.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse('seals:public', args=[seal.token_publico])), 'Selo válido')

    def test_link_defaults_to_pending_and_rejects_owner_mismatch(self):
        response = self.client.post(reverse('operations:link-seal'), self.link_data(proprietario=self.other.pk))
        self.assertContains(response, 'não pertence')
        self.assertFalse(Seal.objects.exists())
        self.client.post(reverse('operations:link-seal'), self.link_data())
        self.assertEqual(Seal.objects.get().status, 'PENDENTE')

    def test_existing_link_is_idempotent_and_preserves_blocked_status_and_token(self):
        seal = Seal.objects.create(veiculo=self.vehicle, numero_serial='s-1234', status='BLOQUEADO')
        token = seal.token_publico
        self.assertEqual(self.client.post(reverse('operations:link-seal'), self.link_data(ativar_apos_vinculo='on')).status_code, 302)
        seal.refresh_from_db()
        self.assertEqual((seal.status, seal.token_publico, seal.validade), ('BLOQUEADO', token, None))
        self.assertEqual(Seal.objects.count(), 1)
        response = self.client.post(reverse('operations:link-seal'), self.link_data(codigo_selo='OUTRO-123'))
        self.assertContains(response, 'já possui um selo')

    def test_other_vehicle_cannot_take_existing_code(self):
        seal = Seal.objects.create(veiculo=self.vehicle, numero_serial='S-1234')
        vehicle = Vehicle.objects.create(proprietario=self.other, placa='DEF4G56', renavam='00000000456', marca='Marca', modelo='Moto', cor='Preta', ano_fabricacao=2025, ano_modelo=2025)
        response = self.client.post(reverse('operations:link-seal'), self.link_data(proprietario=self.other.pk, veiculo=vehicle.pk))
        self.assertContains(response, 'outro veículo')
        seal.refresh_from_db()
        self.assertEqual(seal.veiculo_id, self.vehicle.pk)

    def test_cannot_activate_ineligible_vehicle_person_or_date(self):
        for changes in ({'validade':''}, {'validade':'2000-01-01'}):
            response = self.client.post(reverse('operations:link-seal'), self.link_data(ativar_apos_vinculo='on', **changes))
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Seal.objects.exists())
        self.vehicle.status = 'EM_ANALISE'
        self.vehicle.save()
        self.client.post(reverse('operations:link-seal'), self.link_data(ativar_apos_vinculo='on'))
        self.assertFalse(Seal.objects.exists())

    def test_reports_all_tabs_export_filters_and_formula_safety(self):
        self.person.nome_preferido = ' =HYPERLINK("unsafe")'
        self.person.save()
        Seal.objects.create(veiculo=self.vehicle, numero_serial='EXPIRADO', status='ATIVO', validade=timezone.localdate()-timedelta(days=1))
        for area in ('pessoas','veiculos','documentos','selos','ocorrencias'):
            self.assertEqual(self.client.get(reverse('reports:index'), {'area':area}).status_code, 200)
            response = self.client.get(reverse('reports:csv'), {'area':area})
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response['Cache-Control'])
        export = self.client.get(reverse('reports:csv'), {'area':'pessoas'}).content.decode('utf-8-sig')
        self.assertIn("' =HYPERLINK", export)
        self.assertNotIn('Outra pessoa', self.client.get(reverse('reports:csv'), {'area':'pessoas','q':'HYPERLINK'}).content.decode())
        self.assertContains(self.client.get(reverse('reports:index'), {'area':'selos'}), 'Inválido')
        self.assertEqual(self.client.get(reverse('reports:csv'), {'area':'pessoas','inicio':'2030-01-01','fim':'2020-01-01'}).status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('reports:csv')).status_code, 302)
