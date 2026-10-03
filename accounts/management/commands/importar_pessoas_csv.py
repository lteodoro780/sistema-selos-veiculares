import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Importa ou atualiza pessoas de um CSV UTF-8 separado por vírgula ou ponto e vírgula."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")

    def handle(self, *args, **options):
        path = Path(options["arquivo"])
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")
        created = updated = errors = 0
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(2048)
            stream.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
            for line, row in enumerate(csv.DictReader(stream, dialect=dialect), start=2):
                try:
                    username = (row.get("username") or "").strip().lower()
                    if not username:
                        raise ValueError("username vazio")
                    defaults = {
                        "first_name": (row.get("first_name") or "").strip(),
                        "last_name": (row.get("last_name") or "").strip(),
                        "email": (row.get("email") or "").strip(),
                        "nome_preferido": (row.get("nome_preferido") or "").strip(),
                        "cargo": (row.get("cargo") or "").strip(),
                        "identidade_funcional": (row.get("identidade_funcional") or "").strip(),
                        "organizacao": (row.get("organizacao") or "").strip(),
                        "secao": (row.get("secao") or "").strip(),
                        "is_active": (row.get("ativo") or "1").strip().lower() not in {"0", "false", "nao", "não"},
                    }
                    user, was_created = User.objects.update_or_create(username=username, defaults=defaults)
                    if was_created:
                        user.set_unusable_password()
                        user.save(update_fields=("password",))
                        created += 1
                    else:
                        updated += 1
                except Exception as exc:
                    errors += 1
                    self.stderr.write(f"Linha {line}: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Criados: {created} | Atualizados: {updated} | Erros: {errors}"))
