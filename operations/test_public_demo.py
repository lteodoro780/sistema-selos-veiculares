from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from people.models import Person
from vehicles.models import Vehicle
from seals.models import Seal
from lpr.models import PlatePassage


class PublicDemoTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('demo_test', role='ADMINISTRADOR')
        self.client.force_login(self.admin)

    def test_demo_seed_is_synthetic_and_refuses_existing_data(self):
        call_command('carregar_demo', verbosity=0)
        self.assertEqual(Person.objects.count(), 5)
        self.assertEqual(Vehicle.objects.count(), 5)
        self.assertEqual(PlatePassage.objects.count(), 6)
        self.assertFalse(Person.objects.exclude(username__startswith='demo_').exists())
        self.assertFalse(Person.objects.exclude(telefone='').exists())
        self.assertFalse(PlatePassage.objects.exclude(plate_image='').exists())
        with self.assertRaises(CommandError):
            call_command('carregar_demo', verbosity=0)
        self.assertEqual(Person.objects.count(), 5)

    def test_numeric_creation_collision_and_existing_seal_protection(self):
        call_command('carregar_demo', verbosity=0)
        vehicle = Vehicle.objects.get(placa='DEM5A05')
        data = {'modo':'criar','novo-proprietario':vehicle.proprietario_id,
                'novo-veiculo':vehicle.pk,'novo-validade':(timezone.localdate()+timedelta(days=30)).isoformat(),
                'novo-ativar_apos_vinculo':'on'}
        # O primeiro código já existe. A tentativa seguinte cria um registro novo.
        with patch('operations.seal_workflow._new_numeric_code', side_effect=['10000001','12345678']):
            response = self.client.post(reverse('operations:link-seal'), data)
        self.assertEqual(response.status_code, 302)
        seal = Seal.objects.get(veiculo=vehicle)
        self.assertEqual(seal.numero_serial, '12345678')
        self.assertEqual(seal.status, 'ATIVO')
        response = self.client.get(response['Location'])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '12345678')
        self.assertEqual(self.client.get(reverse('seals:pdf', args=[seal.pk])).status_code, 200)
        self.client.post(reverse('operations:link-seal'), data)
        self.assertEqual(Seal.objects.filter(veiculo=vehicle).count(), 1)

    def test_collector_is_disabled_without_explicit_opt_in(self):
        with patch.dict('os.environ', {'LPR_ENABLED':'false'}), patch('lpr.management.commands.coletar_lpr.CameraClient') as camera:
            with self.assertRaisesMessage(CommandError, 'Coleta desativada'):
                call_command('coletar_lpr')
            camera.assert_not_called()

    def test_people_searches_use_person_records(self):
        call_command('carregar_demo', verbosity=0)
        response = self.client.get(reverse('vehicles:person-search'), {'q':'DEMO-001'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
        response = self.client.get(reverse('operations:occurrence-person-search'), {'q':'DEM1A01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['name'], 'Pessoa Demo A')
