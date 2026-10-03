from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import User
from config.deployment import deployment
from people.models import Person


class DeploymentTests(SimpleTestCase):
    def test_local_must_stay_on_loopback(self):
        self.assertEqual(deployment('local', 'http://127.0.0.1:8004', 8004)[2], 8004)
        for address in ('http://0.0.0.0:8004', 'http://192.0.2.10:8004', 'https://selos.invalid'):
            with self.assertRaises(ValueError):
                deployment('local', address, 8004)

    def test_https_validates_hosts_and_injection(self):
        self.assertEqual(deployment('https', 'https://selos.example.org/', 8004)[0], ['selos.example.org'])
        for address in ('http://selos.example.org', 'https://*.example.org', 'https://a/b',
                        'https://user:secret@a', 'https://192.0.2.20', 'https://localhost',
                        'https://a:8004', 'https://a\n{', 'https://a?x=1', 'https://-host.org'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                deployment('https', address, 8004)


class LinuxAdminTests(TestCase):
    def test_administrator_is_not_a_person_and_no_default_password(self):
        with patch('builtins.input', return_value='gestor'), patch('accounts.management.commands.criar_administrador.getpass', return_value='UmaSenhaPrivada@2026-segura'):
            call_command('criar_administrador', stdout=StringIO())
        admin = User.objects.get(username='gestor')
        self.assertTrue(admin.is_superuser and admin.is_staff and admin.is_active)
        self.assertEqual(admin.role, 'ADMINISTRADOR')
        self.assertTrue(admin.check_password('UmaSenhaPrivada@2026-segura'))
        self.assertFalse(Person.objects.exists())
        with patch('builtins.input', return_value='GESTOR'), self.assertRaises(CommandError):
            call_command('criar_administrador', stdout=StringIO())
        self.assertEqual(User.objects.count(), 1)

    def test_weak_password_is_rejected(self):
        with patch('builtins.input', return_value='gestor'), patch('accounts.management.commands.criar_administrador.getpass', return_value='12345678'), self.assertRaises(CommandError):
            call_command('criar_administrador', stdout=StringIO())
        self.assertFalse(User.objects.exists())

    def test_uploads_require_admin_and_download_as_attachment(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            file = Path(folder) / 'arquivo.html'
            file.write_text('<script>alert(1)</script>', encoding='utf-8')
            self.assertEqual(self.client.get('/media/arquivo.html').status_code, 302)
            admin = User.objects.create_superuser(username='gestor', password='Senha@privada1234')
            self.client.force_login(admin)
            response = self.client.get('/media/arquivo.html')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
            self.assertEqual(response['Content-Type'], 'application/octet-stream')
            self.assertIn('no-store', response['Cache-Control'])
            response.close()
            self.assertEqual(self.client.get('/media/../.env').status_code, 404)
            self.assertEqual(self.client.get('/media/inexistente.pdf').status_code, 404)

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'), ALLOWED_HOSTS=['selos.example.org'], SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_https_proxy_redirect_host_and_cookie(self):
        response = self.client.get('/entrar/', HTTP_HOST='selos.example.org')
        self.assertEqual(response.status_code, 301)
        response = self.client.get('/entrar/', HTTP_HOST='selos.example.org', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies[settings.CSRF_COOKIE_NAME]['secure'])
        self.assertEqual(self.client.get('/entrar/', HTTP_HOST='evil.invalid', HTTP_X_FORWARDED_PROTO='https').status_code, 400)
