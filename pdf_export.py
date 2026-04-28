"""
pdf_export.py — Generates a clean PDF report of rental pricing data.
Uses ReportLab (pure Python, no headless browser needed).
"""

from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

NAVY = colors.HexColor("#111111")
GOLD = colors.HexColor("#d84028")
LIGHT_GREY = colors.HexColor("#F4F5F7")
MID_GREY = colors.HexColor("#8892A4")
WHITE = colors.white


def generate_rental_report(data: Dict[str, Any]) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
    )

    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20, leading=28, textColor=NAVY, spaceAfter=20)
    sub_style = ParagraphStyle("sub", fontName="Helvetica", fontSize=9, leading=14, textColor=MID_GREY, spaceBefore=4, spaceAfter=16)
    section_style = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=12, textColor=NAVY, spaceBefore=14, spaceAfter=6)
    cell_style = ParagraphStyle("cell", fontName="Helvetica", fontSize=8, textColor=NAVY, leading=11)
    cell_bold = ParagraphStyle("cell_bold", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY, leading=11)

    story = []
    scraped_str = data.get("scraped_at", "N/A")
    story.append(Paragraph("Fitzrovia — Competitive Rental Intelligence", title_style))
    story.append(Paragraph(
        f"Midtown Toronto Market Report  ·  {scraped_str}  ·  "
        f"{data.get('total_units', 0)} units tracked across {len(data.get('buildings', []))} buildings",
        sub_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD, spaceAfter=14))

    story.append(Paragraph("Building Overview", section_style))
    bldg_headers = ["Building", "Address", "Last Scraped", "Units", "Bach", "1-Bed", "2-Bed", "3-Bed", "Min Rent", "Max Rent", "Incentives"]
    bldg_rows = [bldg_headers]

    for b in data.get("buildings", []):
        last_scraped = b.get("last_scraped_at")
        if isinstance(last_scraped, datetime):
            last_scraped = last_scraped.strftime("%b %d %H:%M")
        elif isinstance(last_scraped, str):
            last_scraped = last_scraped[:16]
        else:
            last_scraped = "—"

        bldg_rows.append([
            Paragraph(b.get("name", ""), cell_bold),
            Paragraph(b.get("address", ""), cell_style),
            Paragraph(last_scraped, cell_style),
            Paragraph(str(b.get("unit_count", 0)), cell_style),
            Paragraph(str(b.get("bachelor_count", 0)), cell_style),
            Paragraph(str(b.get("one_bed_count", 0)), cell_style),
            Paragraph(str(b.get("two_bed_count", 0)), cell_style),
            Paragraph(str(b.get("three_bed_count", 0)), cell_style),
            Paragraph(f"${b['min_rent']:,.0f}" if b.get("min_rent") else "—", cell_style),
            Paragraph(f"${b['max_rent']:,.0f}" if b.get("max_rent") else "—", cell_style),
            Paragraph((b.get("incentives") or "—")[:60], cell_style),
        ])

    col_widths = [1.4*inch,1.8*inch,0.75*inch,0.45*inch,0.45*inch,0.5*inch,0.5*inch,0.5*inch,0.65*inch,0.65*inch,1.8*inch]
    bldg_table = Table(bldg_rows, colWidths=col_widths, repeatRows=1)
    bldg_table.setStyle(_table_style())
    story.append(bldg_table)

    unit_types = ["Bachelor", "1-Bed", "2-Bed", "3-Bed"]
    for unit_type in unit_types:
        units = data.get("units_by_type", {}).get(unit_type, [])
        if not units:
            continue
        story.append(Paragraph(f"{unit_type} Units — {len(units)} listings", section_style))
        rows = [[Paragraph("Building", cell_bold), Paragraph("Floor Plan", cell_bold), Paragraph("Unit #", cell_bold), Paragraph("Sq Ft", cell_bold), Paragraph("Monthly Rent", cell_bold), Paragraph("Available", cell_bold), Paragraph("Incentives", cell_bold)]]
        for u in sorted(units, key=lambda x: x.get("monthly_rent") or 0):
            rows.append([
                Paragraph(u.get("building_name", ""), cell_bold),
                Paragraph(u.get("floor_plan_name") or "—", cell_style),
                Paragraph(u.get("unit_number") or "—", cell_style),
                Paragraph(str(u.get("sq_ft") or "—"), cell_style),
                Paragraph(f"${u['monthly_rent']:,.0f}" if u.get("monthly_rent") else "—", cell_style),
                Paragraph(u.get("available_date") or "Now", cell_style),
                Paragraph((u.get("incentives") or "—")[:80], cell_style),
            ])
        t = Table(rows, colWidths=[1.5*inch,1.4*inch,0.65*inch,0.55*inch,0.85*inch,0.9*inch,2.1*inch], repeatRows=1)
        t.setStyle(_table_style())
        story.append(KeepTogether([t]))

    story.append(Spacer(1, 0.2*inch))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY, spaceAfter=6))
    footer_style = ParagraphStyle("footer", fontName="Helvetica", fontSize=7, textColor=MID_GREY)
    story.append(Paragraph("Data collected via automated web scraping. Pricing subject to change. For internal use only — Fitzrovia Real Estate Inc.", footer_style))

    doc.build(story, onFirstPage=_page_num, onLaterPages=_page_num)
    return buf.getvalue()


def _table_style():
    return TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 8),
        ("ALIGN", (0,0), (-1,0), "CENTER"),
        ("BOTTOMPADDING", (0,0), (-1,0), 6),
        ("TOPPADDING", (0,0), (-1,0), 6),
        ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,1), (-1,-1), 8),
        ("ALIGN", (0,1), (-1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,1), (-1,-1), 4),
        ("BOTTOMPADDING", (0,1), (-1,-1), 4),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LIGHT_GREY]),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#D0D5DD")),
        ("LINEBELOW", (0,0), (-1,0), 1, GOLD),
    ])


def _page_num(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MID_GREY)
    canvas.drawRightString(doc.pagesize[0] - 0.6*inch, 0.4*inch, f"Page {canvas.getPageNumber()}")
    canvas.drawString(0.6*inch, 0.4*inch, "Fitzrovia Real Estate — Confidential")
    canvas.restoreState()
