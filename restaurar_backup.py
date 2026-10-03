"""Restore only to a fresh code folder. No overwrite or merging of databases."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys
import tempfile
import zipfile


def restore(backup, root):
    root = Path(root).resolve()
    if not (root / 'manage.py').is_file():
        raise ValueError('Extraia primeiro o código em uma pasta nova.')
    for name in ('.env', 'data'):
        path = root / name
        if path.exists() or path.is_symlink():
            raise ValueError('A pasta já contém dados ou configuração. Nada foi substituído.')
    with zipfile.ZipFile(backup) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        required = {'.env', 'data/install-id', 'data/selos.sqlite3', 'manifest.json'}
        if len(names) != len(set(names)) or not required <= set(names) or len(names) > 100000:
            raise ValueError('Estrutura do backup inválida.')
        if sum(e.file_size for e in entries) > 20 * 1024**3:
            raise ValueError('Backup maior que 20 GB: solicite restauração assistida.')
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or ':' in entry.filename:
                raise ValueError('Caminho inválido no backup.')
            if entry.filename not in required and not entry.filename.startswith('data/media/'):
                raise ValueError('Arquivo inesperado no backup.')
        if archive.getinfo('manifest.json').file_size > 20_000_000:
            raise ValueError('Manifesto muito grande.')
        manifest = json.loads(archive.read('manifest.json'))
        if set(manifest['files']) != set(names) - {'manifest.json'}:
            raise ValueError('Manifesto incompleto.')
        with tempfile.TemporaryDirectory(prefix='restore-', dir=root) as folder:
            stage = Path(folder)
            for name, expected in manifest['files'].items():
                file = stage.joinpath(*PurePosixPath(name).parts)
                file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(name) as source, file.open('xb') as target:
                    while block := source.read(1024 * 1024):
                        digest.update(block)
                        target.write(block)
                file.chmod(0o600)
                if digest.hexdigest() != expected:
                    raise ValueError('Backup corrompido. Dados não foram instalados.')
            connection = sqlite3.connect((stage / 'data/selos.sqlite3').as_uri() + '?mode=ro', uri=True)
            try:
                if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or connection.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('Banco inválido no backup.')
            finally:
                connection.close()
            (stage / 'data').rename(root / 'data')
            (stage / '.env').rename(root / '.env')
    print('Backup restaurado na nova pasta. Agora execute INSTALAR_LINUX.sh.')


if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python3 restaurar_backup.py /caminho/backup.zip')
    try:
        restore(sys.argv[1], Path(__file__).resolve().parent)
    except (OSError, ValueError, KeyError, sqlite3.Error, zipfile.BadZipFile) as exc:
        raise SystemExit(f'Não foi possível restaurar: {exc}')
