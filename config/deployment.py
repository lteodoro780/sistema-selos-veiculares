"""Validate the canonical address; never silently enable public HTTP."""
import ipaddress
import re
from urllib.parse import urlsplit


def deployment(mode, origin, port):
    if mode not in {'local', 'https'}:
        raise ValueError('SELOS_MODE deve ser local ou https.')
    port = int(port)
    if not 1024 <= port <= 65535:
        raise ValueError('SELOS_PORT deve estar entre 1024 e 65535.')
    if mode == 'local':
        expected = f'http://127.0.0.1:{port}'
        if origin != expected:
            raise ValueError(f'No modo local, PUBLIC_BASE_URL deve ser {expected}.')
        return ['127.0.0.1', 'localhost'], expected, port
    url = urlsplit(origin)
    host = url.hostname or ''
    if (url.scheme != 'https' or not host or url.username or url.password
            or url.query or url.fragment or url.path not in ('', '/')
            or url.port not in (None, 443) or not re.fullmatch(r'[a-z0-9.-]+', host)
            or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in host.split('.'))):
        raise ValueError('Informe somente https://nome-do-servidor, sem caminho ou porta personalizada.')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('Use um nome DNS com certificado HTTPS confiável, não um IP.')
    if host == 'localhost':
        raise ValueError('Escolha um nome de servidor acessível pelo celular.')
    return [host], f'https://{host}', port
