"""Certificate PDF rendering with ReportLab.

There is exactly ONE template in this project on purpose: the assignment
asks for a single predefined design, not a template editor. Keeping the
layout in one pure function makes it trivial to review, test and restyle.

Layout: landscape A4, double border, centred typographic hierarchy.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# Design tokens (change these to restyle the whole certificate).
NAVY = HexColor("#1F3A5F")
GOLD = HexColor("#B8860B")
GREY = HexColor("#4A4A4A")
PAGE_SIZE = landscape(A4)
PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE


def _draw_letter_spaced_text(
    pdf: canvas.Canvas, text: str, x: float, y: float, font: str, size: float, spacing: float
) -> None:
    """Draw text with extra letter spacing (used for the small header)."""

    pdf.setFont(font, size)
    total_width = pdf.stringWidth(text, font, size) + spacing * (len(text) - 1)
    cursor = x - total_width / 2
    for character in text:
        pdf.drawString(cursor, y, character)
        cursor += pdf.stringWidth(character, font, size) + spacing


def _fitted_font_size(
    text: str, font: str, preferred_size: float, max_width: float
) -> float:
    """Shrink the font until the text fits inside max_width (long names)."""

    size = preferred_size
    while size > 12 and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def generate_certificate_pdf(
    output_path: Path,
    *,
    certificate_title: str,
    recipient_name: str,
    event_name: str,
    event_date: date,
    organization_name: str = "AEREO",
) -> Path:
    """Render one certificate PDF and return the path it was written to."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(output_path), pagesize=PAGE_SIZE)
    pdf.setTitle(f"{certificate_title} - {recipient_name}")
    pdf.setAuthor(organization_name)
    pdf.setSubject(event_name)

    margin = 22
    # --- Double border -------------------------------------------------------
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(4)
    pdf.rect(margin, margin, PAGE_WIDTH - 2 * margin, PAGE_HEIGHT - 2 * margin)

    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.2)
    inner = margin + 10
    pdf.rect(inner, inner, PAGE_WIDTH - 2 * inner, PAGE_HEIGHT - 2 * inner)

    centre_x = PAGE_WIDTH / 2

    # --- Header: organization name ------------------------------------------
    pdf.setFillColor(NAVY)
    _draw_letter_spaced_text(
        pdf, organization_name.upper(), centre_x, PAGE_HEIGHT - 78, "Helvetica-Bold", 15, 4
    )

    # Small decorative divider under the organization name.
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.5)
    pdf.line(centre_x - 60, PAGE_HEIGHT - 92, centre_x + 60, PAGE_HEIGHT - 92)

    # --- Certificate title ---------------------------------------------------
    pdf.setFillColor(NAVY)
    title_size = _fitted_font_size(
        certificate_title, "Helvetica-Bold", 36, PAGE_WIDTH - 140
    )
    pdf.setFont("Helvetica-Bold", title_size)
    pdf.drawCentredString(centre_x, PAGE_HEIGHT - 150, certificate_title)

    # --- Presented-to line ---------------------------------------------------
    pdf.setFillColor(GREY)
    pdf.setFont("Times-Italic", 15)
    pdf.drawCentredString(centre_x, PAGE_HEIGHT - 195, "This certificate is proudly presented to")

    # --- Recipient name ------------------------------------------------------
    pdf.setFillColor(NAVY)
    name_size = _fitted_font_size(recipient_name, "Times-Bold", 40, PAGE_WIDTH - 180)
    pdf.setFont("Times-Bold", name_size)
    name_y = PAGE_HEIGHT - 255
    pdf.drawCentredString(centre_x, name_y, recipient_name)

    # Flourish underline beneath the recipient name.
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1)
    name_half_width = stringWidth(recipient_name, "Times-Bold", name_size) / 2
    pdf.line(centre_x - name_half_width, name_y - 12, centre_x + name_half_width, name_y - 12)

    # --- For participating in ... -------------------------------------------
    pdf.setFillColor(GREY)
    pdf.setFont("Times-Italic", 14)
    pdf.drawCentredString(centre_x, PAGE_HEIGHT - 305, "for participating in")

    pdf.setFillColor(NAVY)
    event_size = _fitted_font_size(event_name, "Helvetica-Bold", 22, PAGE_WIDTH - 180)
    pdf.setFont("Helvetica-Bold", event_size)
    pdf.drawCentredString(centre_x, PAGE_HEIGHT - 340, event_name)

    # --- Date ----------------------------------------------------------------
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 13)
    formatted_date = f"{event_date.strftime('%B')} {event_date.day}, {event_date.year}"
    pdf.drawCentredString(centre_x, PAGE_HEIGHT - 385, f"Date: {formatted_date}")

    # --- Signature / issuing authority area ----------------------------------
    signature_y = 75
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(1)
    left_x = PAGE_WIDTH * 0.28
    right_x = PAGE_WIDTH * 0.72
    pdf.line(left_x - 70, signature_y, left_x + 70, signature_y)
    pdf.line(right_x - 70, signature_y, right_x + 70, signature_y)

    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawCentredString(left_x, signature_y - 18, organization_name)
    pdf.drawCentredString(right_x, signature_y - 18, "Date: " + formatted_date)

    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(left_x, signature_y - 32, "Issued by")
    pdf.drawCentredString(right_x, signature_y - 32, "Event date")

    pdf.save()
    return output_path
