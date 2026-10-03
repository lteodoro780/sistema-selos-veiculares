"""Installation, startup and private backups for this independent instance only."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent


def safe_paths():
    for path in (ROOT / 'data', ROOT / 'backups', ROOT / '.env', ROOT / 'data/selos.sqlite3', ROOT / 'data/install-id', ROOT / 'data/instance.lock'):
        if path.is_symlink():
            raise RuntimeError(f'Link simbólico não permitido: {path.name}')


def initialize():
    safe_paths()
    marker = ROOT / 'data/install-id'
    if not marker.exists():
        if (ROOT / '.env').exists() or (ROOT / 'data/selos.sqlite3').exists():
            raise RuntimeError('Há configuração ou banco de outra instalação. Use uma pasta nova.')
        (ROOT / 'data').mkdir(mode=0o700, exist_ok=True)
        marker.write_text(secrets.token_hex(16), encoding='utf-8')
        marker.chmod(0o600)
    if not (ROOT / '.env').exists():
        if (ROOT / 'data/selos.sqlite3').exists():
            raise RuntimeError('Configuração privada ausente com banco existente. Recupere o .env do backup; não gere outra chave.')
        with (ROOT / '.env').open('x', encoding='utf-8', newline='\n') as file:
            file.write(f'DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\nSELOS_MODE=local\nSELOS_PORT=8004\nPUBLIC_BASE_URL=http://127.0.0.1:8004\n')
        (ROOT / '.env').chmod(0o600)


@contextmanager
def instance_lock():
    safe_paths()
    if not (ROOT / 'data/install-id').is_file():
        raise RuntimeError('Execute INSTALAR_LINUX.sh primeiro.')
    file = (ROOT / 'data/instance.lock').open('a+b')
    if file.tell() == 0:
        file.write(b'0')
        file.flush()
    file.seek(0)
    try:
        try:
            if os.name == 'nt':  # Allows exercising lifecycle tests on Windows.
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Esta instância está em execução. Pare-a antes de instalar, configurar ou fazer backup.') from exc
        yield
    finally:
        file.close()


def django_setup():
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    import django
    django.setup()


def backup():
    """Caller holds instance_lock: database and attachments are quiescent."""
    safe_paths()
    database = ROOT / 'data/selos.sqlite3'
    if not database.is_file():
        raise RuntimeError('Não há banco para copiar. Conclua a instalação primeiro.')
    folder = ROOT / 'backups'
    folder.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = folder / f'selos-{stamp}.zip'
    metadata = {'created_utc': stamp, 'files': {}}
    with tempfile.TemporaryDirectory(prefix='snapshot-', dir=folder) as temporary:
        snapshot = Path(temporary) / 'selos.sqlite3'
        source = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Falha na verificação do banco; backup cancelado.')
        finally:
            target.close()
            source.close()
        files = [(snapshot, 'data/selos.sqlite3'), (ROOT / '.env', '.env'), (ROOT / 'data/install-id', 'data/install-id')]
        media = ROOT / 'data/media'
        if media.exists():
            if media.is_symlink():
                raise RuntimeError('Mídia não pode ser um link simbólico.')
            for path in sorted(media.rglob('*')):
                if path.is_symlink():
                    raise RuntimeError('Mídia contém um link simbólico; revise antes do backup.')
                if path.is_file():
                    files.append((path, path.relative_to(ROOT).as_posix()))
        partial = output.with_suffix('.partial')
        with zipfile.ZipFile(partial, 'x', zipfile.ZIP_DEFLATED) as archive:
            for path, name in files:
                with path.open('rb') as file:
                    metadata['files'][name] = hashlib.file_digest(file, 'sha256').hexdigest()
                archive.write(path, name)
            archive.writestr('manifest.json', json.dumps(metadata, ensure_ascii=False, indent=2))
        partial.chmod(0o600)
        partial.rename(output)
    print('Backup privado criado:', output)
    return output


def prepare(create_admin=False):
    initialize()
    with instance_lock():
        if (ROOT / 'data/selos.sqlite3').exists():
            backup()
        django_setup()
        from django.core.management import call_command
        call_command('check')
        call_command('migrate', interactive=False)
        call_command('collectstatic', interactive=False, verbosity=0)
        call_command('clearsessions')
        if create_admin:
            from accounts.models import User
            from django.db.models import Q
            if not User.objects.filter(Q(is_superuser=True) | Q(role='ADMINISTRADOR'), is_active=True).exists():
                call_command('criar_administrador')
            else:
                print('Administrador existente preservado; nenhuma senha foi alterada.')
        print('Banco preparado. Nenhuma pessoa, veículo ou selo de demonstração foi criado.')


def configure(mode, origin, port):
    from config.deployment import deployment
    _, origin, port = deployment(mode, origin, port)
    from dotenv import dotenv_values
    with instance_lock():
        values = dotenv_values(ROOT / '.env')
        if not values.get('DJANGO_SECRET_KEY'):
            raise RuntimeError('Configuração privada ausente.')
        backup()
        values.update(SELOS_MODE=mode, PUBLIC_BASE_URL=origin, SELOS_PORT=str(port))
        # Only these four validated settings are managed by this package.
        content = ''.join(f'{key}={values[key]}\n' for key in ('DJANGO_SECRET_KEY', 'SELOS_MODE', 'SELOS_PORT', 'PUBLIC_BASE_URL'))
        path = ROOT / '.env'
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', dir=ROOT, prefix='.env-', delete=False) as file:
            file.write(content)
            temporary = Path(file.name)
        temporary.chmod(0o600)
        temporary.replace(path)
    print('Endereço configurado:', origin)
    if mode == 'https':
        print('Configure o proxy e o certificado conforme GUIA_LINUX.md antes de acessar.')
        print('Bloco para o Caddy (não substitua configurações de outros sistemas):')
        print(f'{origin.removeprefix("https://")} {{\n    reverse_proxy 127.0.0.1:{port}\n}}')


def serve():
    with instance_lock():
        django_setup()
        from django.conf import settings
        from django.core.management import call_command
        from django.db.models import Q
        from accounts.models import User
        call_command('migrate', check_unapplied=True, interactive=False, verbosity=0)
        if not User.objects.filter(Q(is_superuser=True) | Q(role='ADMINISTRADOR'), is_active=True).exists():
            raise RuntimeError('Crie o administrador: .venv/bin/python gerenciar_linux.py administrador')
        if not (ROOT / 'staticfiles/admin/css/base.css').exists():
            raise RuntimeError('Arquivos de interface ausentes. Execute INSTALAR_LINUX.sh novamente.')
        # HSTS is deliberately limited to this host, with no preload commitment.
        call_command('check', deploy=settings.HTTPS_ENABLED, fail_level='ERROR')
        from django.core.wsgi import get_wsgi_application
        from waitress import serve as waitress_serve
        options = {'host': '127.0.0.1', 'port': settings.SELOS_PORT, 'threads': 4,
                   'max_request_body_size': 20 * 1024 * 1024, 'clear_untrusted_proxy_headers': True}
        if settings.HTTPS_ENABLED:
            options.update(trusted_proxy='127.0.0.1', trusted_proxy_count=1,
                           trusted_proxy_headers={'x-forwarded-proto', 'x-forwarded-for'})
        print(f'Sistema: {settings.PUBLIC_BASE_URL}', flush=True)
        print('Escutando somente em 127.0.0.1. Para parar, pressione Ctrl+C.', flush=True)
        waitress_serve(get_wsgi_application(), **options)


def main():
    os.umask(0o077)
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description='Gerenciar esta instalação independente de Selos.')
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('instalar', 'preparar', 'iniciar', 'backup', 'administrador', 'patrulhante'):
        sub.add_parser(action)
    https = sub.add_parser('configurar-https')
    https.add_argument('endereco')
    https.add_argument('--porta-interna', type=int, default=8004)
    local = sub.add_parser('configurar-local')
    local.add_argument('--porta', type=int, default=8004)
    args = parser.parse_args()
    if args.action in {'instalar', 'preparar'}:
        prepare(create_admin=args.action == 'instalar')
    elif args.action == 'iniciar':
        serve()
    elif args.action == 'backup':
        with instance_lock():
            backup()
    elif args.action in {'administrador', 'patrulhante'}:
        with instance_lock():
            django_setup()
            from django.core.management import call_command
            call_command('criar_' + args.action)
    elif args.action == 'configurar-https':
        configure('https', args.endereco, args.porta_interna)
    else:
        configure('local', f'http://127.0.0.1:{args.porta}', args.porta)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nOperação interrompida. Nenhum processo de outro sistema foi encerrado.')
        sys.exit(130)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        sys.exit(1)
