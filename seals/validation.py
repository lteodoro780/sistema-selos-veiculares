"""Consulta local: um QR não pode abrir sites nem aprovar um selo por si só."""
import re
from urllib.parse import urlsplit

from django.utils import timezone

from .models import Seal


def parse_seal_code(raw):
    value = (raw or "").strip()
    if not value or len(value) > 2048 or any(ord(char) < 32 for char in value):
        raise ValueError("Informe o número do selo ou leia um QR Code deste sistema.")
    # Extrai apenas o token, nunca acessa o domínio do QR. Assim os selos
    # impressos com localhost também funcionam no leitor do celular.
    if "/" in value or ":" in value:
        try:
            parsed = urlsplit(value)
        except ValueError:
            raise ValueError("O QR Code não contém um endereço de selo reconhecido.")
        if parsed.scheme not in {"", "http", "https"} or (parsed.scheme and not parsed.netloc):
            raise ValueError("O QR Code não pertence ao formato de consulta de selos.")
        match = re.fullmatch(r"/selos/consulta/([A-Za-z0-9_-]{1,64})/?", parsed.path)
        if not match:
            raise ValueError("O QR Code não pertence ao formato de consulta de selos.")
        return {"token_publico": match.group(1)}
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("Código inválido. Digite o número como aparece no selo.")
    return {"token_publico": value} if len(value) > 24 else {"numero_serial__iexact": value}


def seal_validation(seal, today=None):
    today = today or timezone.localdate()
    reasons, pending = [], []
    if seal.status in {Seal.Status.BLOQUEADO, Seal.Status.CANCELADO, Seal.Status.EXPIRADO}:
        reasons.append(f"Selo {seal.get_status_display().lower()} no cadastro.")
    elif seal.status != Seal.Status.ATIVO:
        pending.append("Selo ainda não está ativo.")
    if seal.validade and seal.validade < today:
        reasons.append(f"Prazo do selo encerrado em {seal.validade:%d/%m/%Y}.")
    elif seal.validade is None:
        pending.append("Validade não cadastrada. Confira antes de liberar.")
    vehicle = seal.veiculo
    if vehicle.status in {vehicle.Status.REJEITADO, vehicle.Status.INATIVO}:
        reasons.append(f"Veículo {vehicle.get_status_display().lower()} no cadastro.")
    elif vehicle.status != vehicle.Status.APROVADO:
        pending.append("Veículo ainda não foi aprovado.")
    if not vehicle.proprietario.is_active:
        reasons.append("Cadastro do proprietário está inativo.")
    state = "invalid" if reasons else "attention" if pending else "valid"
    return {
        "state": state,
        "title": {"valid": "Selo válido", "invalid": "Selo inválido", "attention": "Conferência necessária"}[state],
        "symbol": {"valid": "✓", "invalid": "×", "attention": "!"}[state],
        "reasons": reasons + pending or ["Selo ativo, dentro do prazo, com veículo aprovado e proprietário ativo."],
        "checked_at": timezone.now(),
    }
