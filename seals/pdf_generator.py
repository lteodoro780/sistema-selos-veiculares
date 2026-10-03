from io import BytesIO

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


# Cartao vertical inspirado no modelo aprovado para a operacao.
# Mantemos somente fontes nativas do PDF para nao depender de arquivos externos.
PAGE_WIDTH, PAGE_HEIGHT = 90 * mm, 155 * mm

CLASS_STYLES = {
    "GRUPO_A": {
        "primary": "#C62828",
        "dark": "#8E0000",
        "label": "GRUPO A",
        "light_text": True,
    },
    "GRUPO_B": {
        "primary": "#2E7D32",
        "dark": "#145A18",
        "label": "GRUPO B",
        "light_text": True,
    },
    "GRUPO_C": {
        "primary": "#2368AA",
        "dark": "#164B7E",
        "label": "GRUPO_C",
        "light_text": True,
    },
    "PRESTADOR": {
        "primary": "#D9A514",
        "dark": "#775A00",
        "label": "PRESTADOR",
        "light_text": False,
    },
    "SEM_CLASSE": {
        "primary": "#66737D",
        "dark": "#39434A",
        "label": "NAO INFORMADA",
        "light_text": True,
    },
}

DARK = HexColor("#1F2328")
MUTED = HexColor("#66635F")
SOFT_LINE = HexColor("#D6D3CB")
PLATE_BLUE = HexColor("#2368AA")


def draw_qr(pdf, content, x, y, size):
    """Desenha QR vetorial de alto contraste."""
    qr = QrCodeWidget(content)
    x1, y1, x2, y2 = qr.getBounds()
    sx, sy = size / (x2 - x1), size / (y2 - y1)
    drawing = Drawing(size, size, transform=[sx, 0, 0, sy, -x1 * sx, -y1 * sy])
    drawing.add(qr)
    renderPDF.draw(drawing, pdf, x, y)


def _fit_centered(pdf, text, y, max_width, max_size, min_size=7, font="Helvetica-Bold"):
    text = str(text or "").strip()
    size = float(max_size)
    while size > min_size and pdf.stringWidth(text, font, size) > max_width:
        size -= 0.5
    pdf.setFont(font, size)
    pdf.drawCentredString(PAGE_WIDTH / 2, y, text)
    return size


def _fit_left(pdf, text, x, y, max_width, max_size, min_size=6.5, font="Helvetica"):
    text = str(text or "").strip()
    size = float(max_size)
    while size > min_size and pdf.stringWidth(text, font, size) > max_width:
        size -= 0.5
    pdf.setFont(font, size)
    pdf.drawString(x, y, text)
    return size


def _fit_right(pdf, text, x, y, max_width, max_size, min_size=6.5, font="Helvetica"):
    text = str(text or "").strip()
    size = float(max_size)
    while size > min_size and pdf.stringWidth(text, font, size) > max_width:
        size -= 0.5
    pdf.setFont(font, size)
    pdf.drawRightString(x, y, text)
    return size


def _person_identification(owner):
    rank = (getattr(owner, "cargo", "") or "").strip()
    name = (getattr(owner, "nome_exibicao", "") or "").strip()
    if rank and name:
        return f"{rank} {name}".upper()
    return (name or rank or "PROPRIETARIO NAO INFORMADO").upper()


def _vehicle_description(vehicle):
    parts = []
    brand = (getattr(vehicle, "marca", "") or "").strip()
    model = (getattr(vehicle, "modelo", "") or "").strip()
    color = (getattr(vehicle, "cor", "") or "").strip()
    main = " ".join(part for part in (brand, model) if part)
    if main:
        parts.append(main)
    if color:
        parts.append(color.lower())
    return " - ".join(parts) if parts else "NAO INFORMADO"


def _validity_label(seal):
    validity = getattr(seal, "validade", None)
    if not validity:
        return "NAO DEFINIDA"
    return validity.strftime("%m/%Y")


def _draw_plate(pdf, vehicle):
    x = 12 * mm
    y = 88.5 * mm
    width = PAGE_WIDTH - 24 * mm
    height = 19.5 * mm
    radius = 3.2 * mm
    band_h = 5.2 * mm

    # Fundo azul arredondado; o branco recobre a porcao inferior, mantendo cantos superiores azuis.
    pdf.setFillColor(PLATE_BLUE)
    pdf.setStrokeColor(DARK)
    pdf.setLineWidth(1.2)
    pdf.roundRect(x, y, width, height, radius, fill=1, stroke=0)

    pdf.setFillColor(white)
    pdf.rect(x, y, width, height - band_h + 0.3 * mm, fill=1, stroke=0)

    pdf.setStrokeColor(DARK)
    pdf.setLineWidth(1.15)
    pdf.roundRect(x, y, width, height, radius, fill=0, stroke=1)

    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawCentredString(PAGE_WIDTH / 2, y + height - 3.8 * mm, "BRASIL")

    pdf.setFillColor(DARK)
    plate = (getattr(vehicle, "placa", "") or "SEMPLACA").upper()
    _fit_centered(
        pdf,
        plate,
        y + 4.2 * mm,
        width - 8 * mm,
        24,
        15,
        "Courier-Bold",
    )


def generate_seal_pdf(seal):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT), pageCompression=1)

    vehicle = seal.veiculo
    owner = vehicle.proprietario
    style = CLASS_STYLES.get(getattr(owner, "classe_funcional", ""), CLASS_STYLES["SEM_CLASSE"])
    primary = HexColor(style["primary"])
    dark_primary = HexColor(style["dark"])
    header_text = white if style["light_text"] else DARK

    # Fundo da pagina e linha de corte.
    pdf.setFillColor(white)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setDash(3.5, 2.5)
    pdf.setStrokeColor(HexColor("#6A6A6A"))
    pdf.setLineWidth(0.55)
    pdf.rect(1.5 * mm, 1.5 * mm, PAGE_WIDTH - 3 * mm, PAGE_HEIGHT - 3 * mm)
    pdf.setDash()

    # Cartao: a cor da classe aparece no cabecalho e no rodape.
    card_x = 3.5 * mm
    card_y = 3.5 * mm
    card_w = PAGE_WIDTH - 7 * mm
    card_h = PAGE_HEIGHT - 7 * mm
    radius = 6 * mm

    pdf.setFillColor(primary)
    pdf.setStrokeColor(dark_primary)
    pdf.setLineWidth(0.75)
    pdf.roundRect(card_x, card_y, card_w, card_h, radius, fill=1, stroke=1)

    # Miolo branco; deixa 25 mm de cabecalho e 9.5 mm de rodape coloridos.
    body_bottom = 13 * mm
    body_top = 127 * mm
    pdf.setFillColor(white)
    pdf.rect(card_x, body_bottom, card_w, body_top - body_bottom, fill=1, stroke=0)

    # Identidade genérica SV em um círculo.
    emblem_x = 14.5 * mm
    emblem_y = 139.5 * mm
    emblem_r = 7.5 * mm
    pdf.setStrokeColor(header_text)
    pdf.setLineWidth(1.0)
    pdf.circle(emblem_x, emblem_y, emblem_r, fill=0, stroke=1)
    pdf.setFillColor(header_text)
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawCentredString(emblem_x, emblem_y - 3.3, "SV")

    text_x = 27.5 * mm
    pdf.setFillColor(header_text)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(text_x, 145.0 * mm, "CLASSE")

    class_label = style["label"]
    size = 18.5
    max_class_width = PAGE_WIDTH - text_x - 7 * mm
    while size > 10 and pdf.stringWidth(class_label, "Helvetica-Bold", size) > max_class_width:
        size -= 0.5
    pdf.setFont("Helvetica-Bold", size)
    pdf.drawString(text_x, 134.5 * mm, class_label)

    # Identificacao principal da pessoa.
    pdf.setFillColor(DARK)
    _fit_centered(pdf, _person_identification(owner), 117.3 * mm, 74 * mm, 18.5, 10.5)
    pdf.setFillColor(MUTED)
    subtitle = "Cargo e nome preferido" if getattr(owner, "vinculo", "COLABORADOR") == "COLABORADOR" else "Identificacao do proprietario"
    _fit_centered(pdf, subtitle, 110.4 * mm, 72 * mm, 9, 7, "Helvetica")

    # Placa em destaque.
    _draw_plate(pdf, vehicle)

    # Dados resumidos do veiculo e validade.
    left_x = 12 * mm
    right_x = PAGE_WIDTH - 12 * mm
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.2)
    pdf.drawString(left_x, 82.3 * mm, "MODELO")
    pdf.drawRightString(right_x, 82.3 * mm, "VALIDO ATE")

    pdf.setFillColor(DARK)
    _fit_left(pdf, _vehicle_description(vehicle), left_x, 75.7 * mm, 45 * mm, 10.5, 7.2, "Helvetica")
    _fit_right(pdf, _validity_label(seal), right_x, 75.7 * mm, 26 * mm, 10.5, 7.2, "Helvetica")

    # QR - com moldura branca discreta para preservar a zona de silencio.
    qr_box = 41 * mm
    qr_size = 35.5 * mm
    qr_box_x = (PAGE_WIDTH - qr_box) / 2
    qr_box_y = 33.5 * mm
    pdf.setFillColor(white)
    pdf.setStrokeColor(SOFT_LINE)
    pdf.setLineWidth(0.6)
    pdf.roundRect(qr_box_x, qr_box_y, qr_box, qr_box, 2.2 * mm, fill=1, stroke=1)
    draw_qr(
        pdf,
        seal.url_publica,
        (PAGE_WIDTH - qr_size) / 2,
        qr_box_y + (qr_box - qr_size) / 2,
        qr_size,
    )

    pdf.setFillColor(MUTED)
    _fit_centered(pdf, "Escaneie para conferir o status", 28.4 * mm, 70 * mm, 8.2, 6.8, "Helvetica")

    # Codigo de consulta preserva exatamente o valor do banco.
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.0)
    pdf.drawCentredString(PAGE_WIDTH / 2, 21.9 * mm, "CODIGO DE CONSULTA")
    pdf.setFillColor(DARK)
    _fit_centered(pdf, seal.numero_serial, 14.9 * mm, 67 * mm, 15.5, 8.5, "Courier")

    # Rodape sem criar um segundo identificador de selo.
    pdf.setFillColor(header_text)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawCentredString(PAGE_WIDTH / 2, 7.1 * mm, "SELO VEICULAR - DEMO")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()
