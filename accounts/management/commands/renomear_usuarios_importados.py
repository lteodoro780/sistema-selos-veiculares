from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.csv_import import _generated_username
from people.models import Person as User


class Command(BaseCommand):
    help = "Troca o prefixo imp_ pela cargo nos usuários importados da planilha histórica."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        renamed = skipped = 0
        for user in User.objects.filter(username__startswith="imp_").order_by("pk"):
            name = user.nome_preferido or user.get_full_name() or user.username.removeprefix("imp_").rsplit("_", 1)[0]
            new_username = _generated_username(name, user.secao, user.cargo)
            if User.objects.filter(username__iexact=new_username).exclude(pk=user.pk).exists():
                skipped += 1
                continue
            if not options["dry_run"]:
                user.username = new_username
                user.save(update_fields=("username",))
            renamed += 1
        if options["dry_run"]:
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(f"{renamed} usuário(s) preparado(s); {skipped} ignorado(s)."))
