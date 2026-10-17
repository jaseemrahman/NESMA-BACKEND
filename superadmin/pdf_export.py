"""
Branded PDF table export for the admin panel (landscape A4, NIT logo, filters, page numbers).
Arabic text is shaped + re-ordered so it renders correctly with the bundled DejaVu Sans font.
"""
import io
import re
from pathlib import Path
from xml.sax.saxutils import escape

import arabic_reshaper
from bidi.algorithm import get_display
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ASSETS = Path(__file__).resolve().parent / 'pdf_assets'
LOGO = ASSETS / 'nit-logo.png'
NAVY = colors.HexColor('#2E368F')
CYAN = colors.HexColor('#81D1E8')
INK = colors.HexColor('#1E293B')
MUTED = colors.HexColor('#64748B')
LINE = colors.HexColor('#D9DCF0')
ZEBRA = colors.HexColor('#F5F6FC')
ROWS_PER_TABLE = 250  # many small tables paginate far faster than one huge table
ARABIC_RE = re.compile(r'[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]')

_fonts_registered = False


def register_fonts():
    global _fonts_registered
    if not _fonts_registered:
        pdfmetrics.registerFont(TTFont('DejaVu', str(ASSETS / 'DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont('DejaVu-Bold', str(ASSETS / 'DejaVuSans-Bold.ttf')))
        pdfmetrics.registerFontFamily('DejaVu', normal='DejaVu', bold='DejaVu-Bold')
        _fonts_registered = True


def pdf_text(value):
    """Escape for ReportLab markup; shape + bidi-reorder Arabic so it is readable."""
    text = '' if value is None else str(value)
    if ARABIC_RE.search(text):
        text = get_display(arabic_reshaper.reshape(text))
    return escape(text).replace('\n', '<br/>')


def pdf_response(filename, title, headers, rows, col_widths, filters=None, total=None):
    """
    Build a PDF table report.
    `rows` may be any iterable (e.g. a generator streaming from the database); `col_widths` are relative
    weights; `filters` is a list of (label, value) shown under the title; `total` is the record count.
    """
    register_fonts()
    cell = ParagraphStyle('cell', fontName='DejaVu', fontSize=7.6, leading=9.6, textColor=INK)
    head = ParagraphStyle('head', parent=cell, fontName='DejaVu-Bold', textColor=colors.white)
    title_style = ParagraphStyle('title', fontName='DejaVu-Bold', fontSize=15, leading=19, textColor=NAVY)
    meta_style = ParagraphStyle('meta', fontName='DejaVu', fontSize=8.2, leading=11, textColor=MUTED)

    generated = timezone.localtime()
    page_w, page_h = landscape(A4)
    usable = page_w - 24 * mm
    total = sum(col_widths)
    widths = [usable * w / total for w in col_widths]

    header_row = [Paragraph(pdf_text(h), head) for h in headers]
    base_style = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, LINE),
        ('BOX', (0, 0), (-1, -1), 0.6, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]

    def make_table(chunk):
        data = [header_row] + chunk
        table = Table(data, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle(base_style + [('BACKGROUND', (0, i), (-1, i), ZEBRA) for i in range(2, len(data), 2)]))
        return table

    tables, chunk, count = [], [], 0
    for row in rows:
        chunk.append([Paragraph(pdf_text(v), cell) for v in row])
        count += 1
        if len(chunk) == ROWS_PER_TABLE:
            tables.append(make_table(chunk))
            chunk = []
    if chunk or not tables:
        tables.append(make_table(chunk))

    filter_text = ' &nbsp;|&nbsp; '.join(f'<b>{pdf_text(k)}:</b> {pdf_text(v)}' for k, v in (filters or []))
    story = [
        Paragraph(pdf_text(title), title_style),
        Spacer(1, 3),
        Paragraph(f'{total if total is not None else count:,} record(s) &nbsp;|&nbsp; Generated {generated:%d %b %Y, %I:%M %p}'
                  + (f' &nbsp;|&nbsp; {filter_text}' if filter_text else ''), meta_style),
        Spacer(1, 8),
        *tables,
    ]

    def decorate(canvas, doc):
        canvas.saveState()
        # header: logo on the left, cyan rule underneath
        logo_h = 9 * mm
        canvas.drawImage(str(LOGO), 12 * mm, page_h - 6 * mm - logo_h, height=logo_h, width=logo_h * 838 / 157,
                         mask='auto', preserveAspectRatio=True)
        canvas.setFont('DejaVu', 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(page_w - 12 * mm, page_h - 11 * mm, 'Admin Panel Report')
        canvas.setStrokeColor(CYAN)
        canvas.setLineWidth(1.4)
        canvas.line(12 * mm, page_h - 17.5 * mm, page_w - 12 * mm, page_h - 17.5 * mm)
        # footer
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(12 * mm, 11 * mm, page_w - 12 * mm, 11 * mm)
        canvas.drawString(12 * mm, 7 * mm, 'Nesma Infrastructure & Technology - Confidential')
        canvas.drawRightString(page_w - 12 * mm, 7 * mm, f'Page {doc.page}')
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=22 * mm, bottomMargin=15 * mm, title=title, author='NIT Admin Panel',
    )
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}_{generated:%Y%m%d_%H%M}.pdf"'
    return response
