from datetime import timedelta
from django.conf import settings

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from people.models import Person
from vehicles.models import Vehicle
from .models import Seal, SealScan
from .validation import parse_seal_code, seal_validation


class MobileSealTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='operator', password='TesteSomente123!', role='ADMINISTRADOR')
        cls.person = Person.objects.create(username='mobile-person', nome_preferido='PESSOA TESTE', cargo='COLABORADOR')
        cls.vehicle = Vehicle.objects.create(proprietario=cls.person, placa='ABC1D23', marca='Marca', modelo='Modelo', cor='Verde', ano_fabricacao=2025, ano_modelo=2025, status=Vehicle.Status.APROVADO)
        cls.seal = Seal.objects.create(veiculo=cls.vehicle, numero_serial='TESTE-123', status=Seal.Status.ATIVO, validade=timezone.localdate() + timedelta(days=30))

    def setUp(self):
        self.client.force_login(self.admin)

    def test_scanner_requires_operator(self):
        self.client.logout()
        for url in (reverse('seals:mobile'), reverse('seals:public', args=[self.seal.token_publico])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith('/entrar/'))
            self.assertNotContains(response, self.person.nome_preferido, status_code=302)
        person_account = User.objects.create_user(username='nonoperator', is_staff=True, role='USUARIO')
        self.client.force_login(person_account)
        self.assertEqual(self.client.get(reverse('seals:mobile')).status_code, 302)

    def test_scanner_has_camera_manual_photo_and_security_headers(self):
        response = self.client.get(reverse('seals:mobile'))
        self.assertContains(response, 'Abrir câmera')
        self.assertContains(response, 'Escolher foto')
        self.assertContains(response, 'Consultar no banco')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Permissions-Policy'], 'camera=(self), microphone=(), geolocation=()')

    def test_serial_and_legacy_qr_lookup(self):
        for value in ('teste-123', self.seal.token_publico, 'http://127.0.0.1:8001/selos/consulta/' + self.seal.token_publico + '/', 'https://endereco-antigo.invalid/selos/consulta/' + self.seal.token_publico + '/?legacy=1'):
            with self.subTest(value=value):
                response = self.client.post(reverse('seals:mobile'), {'code': value}, follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Selo válido')
                self.assertContains(response, 'ABC1D23')
                self.assertEqual(response.redirect_chain[0][0], reverse('seals:public', args=[self.seal.token_publico]))
        self.assertEqual(SealScan.objects.count(), 4)

    def test_unrecognized_codes_never_approve_or_redirect(self):
        for value in ('', 'INEXISTENTE-123', 'javascript:alert(1)', 'https://site.invalid/', 'a' * 2049, '<script>alert(1)</script>'):
            with self.subTest(value=value[:40]):
                response = self.client.post(reverse('seals:mobile'), {'code': value})
                self.assertEqual(response.status_code, 400)
                self.assertNotContains(response, 'Selo válido', status_code=400)
                self.assertNotIn('Location', response)
        self.assertFalse(SealScan.objects.exists())

    def test_missing_token_is_a_friendly_not_found(self):
        response = self.client.get(reverse('seals:public', args=['inexistente']))
        self.assertContains(response, 'Selo não encontrado', status_code=404)
        self.assertIn('no-store', response['Cache-Control'])

    def test_lookup_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse('seals:mobile'), {'code': self.seal.numero_serial}).status_code, 403)

    def test_same_origin_post_works_with_csrf_and_other_origins_fail(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        client.get(reverse('seals:mobile'))
        csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        data = {'code': self.seal.numero_serial, 'csrfmiddlewaretoken': csrf}
        self.assertEqual(client.post(reverse('seals:mobile'), data, HTTP_ORIGIN='http://testserver').status_code, 302)
        for origin in ('null', 'https://site-externo.invalid'):
            self.assertEqual(client.post(reverse('seals:mobile'), data, HTTP_ORIGIN=origin).status_code, 403)

    def test_results_are_not_cached(self):
        response = self.client.get(reverse('seals:public', args=[self.seal.token_publico]))
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        self.assertContains(response, 'Consultado em')
        self.assertContains(response, 'Atualizar consulta')

    def test_valid_until_end_of_expiry_day(self):
        self.seal.validade = timezone.localdate()
        self.assertEqual(seal_validation(self.seal)['state'], 'valid')

    def test_active_but_date_expired_is_invalid(self):
        self.seal.validade = timezone.localdate() - timedelta(days=1)
        result = seal_validation(self.seal)
        self.assertEqual(result['state'], 'invalid')
        self.assertIn('Prazo', result['reasons'][0])

    def test_inactive_seal_states(self):
        for state in (Seal.Status.BLOQUEADO, Seal.Status.CANCELADO, Seal.Status.EXPIRADO):
            self.seal.status = state
            self.assertEqual(seal_validation(self.seal)['state'], 'invalid')
        self.seal.status = Seal.Status.PENDENTE
        self.assertEqual(seal_validation(self.seal)['state'], 'attention')

    def test_no_expiry_needs_review(self):
        self.seal.validade = None
        self.assertEqual(seal_validation(self.seal)['state'], 'attention')

    def test_unapproved_vehicle_never_green(self):
        for status, expected in ((Vehicle.Status.EM_ANALISE, 'attention'), (Vehicle.Status.INATIVO, 'invalid'), (Vehicle.Status.REJEITADO, 'invalid')):
            self.seal.veiculo.status = status
            self.assertEqual(seal_validation(self.seal)['state'], expected)

    def test_inactive_person_invalidates_result_without_mutating_seal(self):
        self.seal.veiculo.proprietario.is_active = False
        self.assertEqual(seal_validation(self.seal)['state'], 'invalid')
        self.seal.refresh_from_db()
        self.assertEqual(self.seal.status, Seal.Status.ATIVO)


class CodeParserTests(SimpleTestCase):
    def test_rejects_malformed_urls_and_control_characters(self):
        for value in ('https://[bad/selos/consulta/a/', 'file:///selos/consulta/a/', '/selos/consulta/a/extra/', '/selos/consulta/a%2Fb/', 'TESTE\n123', '/admin/'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_seal_code(value)

    def test_accepts_local_path(self):
        self.assertEqual(parse_seal_code('/selos/consulta/ABC_123-/'), {'token_publico': 'ABC_123-'})

    def test_linux_uses_dns_https_not_the_windows_temporary_ip_launcher(self):
        from config.deployment import deployment
        for host in ('0.0.0.0', '8.8.8.8', 'https://site.invalid', '::', '169.254.0.1'):
            with self.assertRaises(ValueError):
                deployment('https', f'https://{host}', 8004)
        self.assertEqual(deployment('https', 'https://selos.example.org', 8004)[1], 'https://selos.example.org')
