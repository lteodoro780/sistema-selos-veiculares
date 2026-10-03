"""Cria somente registros sintéticos, sem acessar câmera ou enviar mensagens."""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from people.models import Person
from vehicles.models import Vehicle
from seals.models import Seal
from operations.models import Occurrence
from lpr.models import PlatePassage


class Command(BaseCommand):
    help = 'Carrega cinco pessoas fictícias e cenários demonstráveis em uma instalação vazia.'

    @transaction.atomic
    def handle(self, *args, **options):
        if Person.objects.exists() or Vehicle.objects.exists() or PlatePassage.objects.exists() or Occurrence.objects.exists() or Seal.objects.exists():
            raise CommandError('A demonstração exige banco vazio de registros operacionais. Nenhum dado foi alterado.')
        operator = User.objects.filter(is_active=True, role=User.Role.ADMINISTRADOR).first()
        if not operator:
            raise CommandError('Crie primeiro seu administrador; não há usuário ou senha padrão.')
        now = timezone.now()
        for i, (name, vehicle_type, group, status) in enumerate([
            ('Pessoa Demo A', 'CARRO', 'GRUPO_A', 'ATIVO'),
            ('Pessoa Demo B', 'MOTO', 'GRUPO_B', 'ATIVO'),
            ('Pessoa Demo C', 'CARRO', 'GRUPO_C', 'BLOQUEADO'),
            ('Pessoa Demo D', 'CAMINHONETE', 'PRESTADOR', 'PENDENTE'),
            ('Pessoa Demo E', 'CARRO', 'SEM_CLASSE', ''),
        ], 1):
            person = Person.objects.create(
                username=f'demo_{i}', first_name=name, nome_preferido=name,
                email=f'pessoa{i}@example.invalid', vinculo='COLABORADOR',
                classe_funcional=group, cargo='Colaborador Demo',
                identidade_funcional=f'DEMO-{i:03}', organizacao='Organização Demo',
                secao='Setor Demonstrativo', ramal=f'{i:04}',
                cadastro_aprovado=True, review_status='VERIFIED',
            )
            vehicle = Vehicle.objects.create(
                proprietario=person, placa=f'DEM{i}A0{i}', renavam=f'{i:011}',
                tipo=vehicle_type, marca='Marca Demo', modelo=f'Modelo {i}',
                cor=['Prata', 'Azul', 'Branco', 'Cinza', 'Verde'][i-1],
                ano_fabricacao=2024, ano_modelo=2024, status='APROVADO',
            )
            seal = None
            if status:
                seal = Seal.objects.create(
                    veiculo=vehicle, numero_serial=str(10000000+i), status=status,
                    validade=timezone.localdate()+timedelta(days=365), emitido_por=operator,
                )
            PlatePassage.objects.create(
                captured_at=now-timedelta(minutes=i*7), raw_plate=vehicle.placa,
                plate=vehicle.placa, plate_format='MERCOSUL', match_method='EXATA',
                vehicle=vehicle, person=person, camera_name='Câmera Simulada',
                camera_ip='192.0.2.1', lane='1', camera_direction='forward',
                movement='ENTRADA' if i%2 else 'SAIDA', pic_name=f'demo-passagem-{i}',
                matched_automatically=True,
                seal_serial_snapshot=seal.numero_serial if seal else '',
                seal_status_snapshot=seal.status if seal else '',
            )
            if i == 3:
                Occurrence.objects.create(
                    numero='OC-DEMO-001', proprietario=person, veiculo=vehicle, selo=seal,
                    tipo='SELO_DANIFICADO', status='ABERTA', local='Portaria Demo',
                    descricao='Cenário fictício: selo danificado durante demonstração.',
                    providencias='Solicitar substituição do selo de exemplo.', registrado_por=operator,
                )
        PlatePassage.objects.create(
            captured_at=now, raw_plate='DEM1001', plate='DEM1001',
            plate_format='MERCOSUL', match_method='REVISAO',
            match_note='Cenário fictício para revisão manual: corrigir para DEM1A01.',
            camera_name='Câmera Simulada', camera_ip='192.0.2.1',
            movement='PASSAGEM', pic_name='demo-revisao',
        )
        self.stdout.write(self.style.SUCCESS('Demo criada: 5 pessoas, 5 veículos, 4 selos, 6 passagens e 1 ocorrência. Nenhuma câmera foi acessada.'))
