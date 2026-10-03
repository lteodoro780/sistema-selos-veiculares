from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Cria um administrador com senha escolhida na instalação, sem credenciais padrão.'
    role = 'ADMINISTRADOR'
    label = 'administrador'

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            name = input(f'Nome de acesso do {self.label}: ').strip()
            if not name:
                raise CommandError('Informe o nome de acesso.')
            administrator = self.role == User.Role.ADMINISTRADOR
            user = User(username=name, role=self.role,
                        is_staff=administrator, is_superuser=administrator, is_active=True, cadastro_aprovado=True)
            User._meta.get_field('username').clean(name, user)
            if User.objects.filter(username__iexact=name).exists():
                raise CommandError('Esse nome já existe. Nenhuma conta foi alterada.')
            password = getpass('Senha (não será exibida): ')
            if password != getpass('Repita a senha: '):
                raise CommandError('As senhas não conferem. Execute novamente.')
            validate_password(password, user)
            user.set_password(password)
            user.full_clean(exclude=['password'])
            user.save()
        except EOFError as exc:
            raise CommandError('Use um terminal interativo para criar o administrador.') from exc
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        self.stdout.write(self.style.SUCCESS(f'{self.label.capitalize()} criado. A senha não foi salva em texto.'))
