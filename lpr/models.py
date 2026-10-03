from django.conf import settings
from django.db import models


class PlatePassage(models.Model):
    class Movement(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saída"
        PASSAGEM = "PASSAGEM", "Passagem"

    class CameraDirection(models.TextChoices):
        FORWARD = "forward", "Frente"
        REVERSE = "reverse", "Reverso"
        UNKNOWN = "unknown", "Desconhecida"

    class PlateFormat(models.TextChoices):
        ANTIGA = "ANTIGA", "Padrão antigo"
        MERCOSUL = "MERCOSUL", "Mercosul"
        DESCONHECIDA = "DESCONHECIDA", "Desconhecido"

    class MatchMethod(models.TextChoices):
        EXATA = "EXATA", "Leitura exata"
        OCR = "OCR", "Correção OCR"
        MANUAL = "MANUAL", "Correção manual"
        APRENDIDA = "APRENDIDA", "Regra manual aprendida"
        NAO_ENCONTRADA = "NAO_ENCONTRADA", "Não cadastrada"
        REVISAO = "REVISAO", "Revisão necessária"

    captured_at = models.DateTimeField("data/hora", db_index=True)
    raw_plate = models.CharField("placa lida pela câmera", max_length=12, blank=True, db_index=True)
    plate = models.CharField("placa identificada", max_length=12, db_index=True)
    plate_format = models.CharField(
        "padrão da placa", max_length=20, choices=PlateFormat.choices,
        default=PlateFormat.DESCONHECIDA, db_index=True,
    )
    match_method = models.CharField(
        "método de vínculo", max_length=24, choices=MatchMethod.choices,
        default=MatchMethod.NAO_ENCONTRADA, db_index=True,
    )
    match_note = models.CharField("detalhe da leitura", max_length=255, blank=True)
    vehicle = models.ForeignKey(
        "vehicles.Vehicle", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="lpr_passages", verbose_name="veículo",
    )
    person = models.ForeignKey(
        "people.Person", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="lpr_passages", verbose_name="proprietário",
    )
    camera_name = models.CharField("câmera", max_length=120)
    camera_ip = models.GenericIPAddressField("IP da câmera")
    lane = models.CharField("faixa", max_length=20, blank=True)
    camera_direction = models.CharField(
        "direção da câmera", max_length=20, choices=CameraDirection.choices,
        default=CameraDirection.UNKNOWN,
    )
    movement = models.CharField(
        "movimento", max_length=20, choices=Movement.choices,
        default=Movement.PASSAGEM, db_index=True,
    )
    pic_name = models.CharField("identificador da imagem", max_length=80)
    plate_image = models.ImageField("imagem da placa", upload_to="lpr/", blank=True)
    raw_country = models.CharField("país informado pela câmera", max_length=20, blank=True)
    matched_automatically = models.BooleanField("vínculo automático", default=False)
    seal_serial_snapshot = models.CharField("selo no momento", max_length=24, blank=True)
    seal_status_snapshot = models.CharField("situação do selo no momento", max_length=20, blank=True)
    manual_note = models.CharField("observação da correção manual", max_length=255, blank=True)
    manual_corrected_at = models.DateTimeField("corrigida manualmente em", null=True, blank=True)
    manual_corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lpr_manual_corrections",
        verbose_name="corrigida manualmente por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-captured_at", "-pk")
        verbose_name = "movimentação de placa"
        verbose_name_plural = "movimentações de placas"
        constraints = [
            models.UniqueConstraint(
                fields=("camera_ip", "pic_name"),
                name="lpr_unique_camera_picture",
            )
        ]

    def save(self, *args, **kwargs):
        self.raw_plate = "".join(ch for ch in (self.raw_plate or "").upper() if ch.isalnum())
        self.plate = "".join(ch for ch in (self.plate or "").upper() if ch.isalnum())
        super().save(*args, **kwargs)

    @property
    def is_matched(self):
        return self.vehicle_id is not None

    @property
    def was_ocr_corrected(self):
        return self.match_method == self.MatchMethod.OCR and self.raw_plate != self.plate

    @property
    def was_manually_corrected(self):
        return self.match_method == self.MatchMethod.MANUAL

    def __str__(self):
        return f"{self.plate} — {self.captured_at:%d/%m/%Y %H:%M:%S}"


class PlateCorrectionRule(models.Model):
    raw_plate = models.CharField("leitura da câmera", max_length=12, db_index=True)
    corrected_plate = models.CharField("placa correta", max_length=12, db_index=True)
    camera_ip = models.CharField(
        "IP da câmera", max_length=45, blank=True, default="",
        help_text="Vazio aplica a qualquer câmera; normalmente a regra é criada para a câmera da passagem.",
    )
    active = models.BooleanField("ativa", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lpr_correction_rules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("raw_plate", "camera_ip")
        verbose_name = "regra manual de placa"
        verbose_name_plural = "regras manuais de placas"
        constraints = [
            models.UniqueConstraint(
                fields=("raw_plate", "camera_ip"),
                name="lpr_unique_manual_rule_by_camera",
            )
        ]

    def save(self, *args, **kwargs):
        self.raw_plate = "".join(ch for ch in (self.raw_plate or "").upper() if ch.isalnum())
        self.corrected_plate = "".join(ch for ch in (self.corrected_plate or "").upper() if ch.isalnum())
        self.camera_ip = (self.camera_ip or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        scope = self.camera_ip or "todas as câmeras"
        return f"{self.raw_plate} → {self.corrected_plate} ({scope})"
