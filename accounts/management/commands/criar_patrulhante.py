from .criar_administrador import Command as CreateAdministrator


class Command(CreateAdministrator):
    help = 'Cria um patrulhante para o portal, sem acesso ao Django Admin.'
    role = 'PATRULHANTE'
    label = 'patrulhante'
