from __future__ import annotations

import io
import re
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from leadpilot.application.proposal_pdf_snapshot import ProposalPdfSnapshot


def _text(value: object) -> str:
    clean = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "?", str(value))
    return clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ReportLabProposalPdfRenderer:
    def render(self, snapshot: ProposalPdfSnapshot, *, confidential: bool) -> bytes:
        output = io.BytesIO()
        doc = BaseDocTemplate(
            output,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            title=snapshot.proposal["title"],
            author=snapshot.branding.display_name,
        )
        frame = Frame(
            doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal"
        )
        doc.addPageTemplates(
            PageTemplate(
                id="proposal",
                frames=frame,
                onPage=lambda canvas, document: self._page(
                    canvas, document, snapshot, confidential
                ),
            )
        )
        styles = getSampleStyleSheet()
        primary = colors.HexColor(snapshot.branding.primary_color)
        heading = ParagraphStyle(
            "BrandHeading",
            parent=styles["Heading1"],
            textColor=primary,
            spaceBefore=10,
            spaceAfter=8,
            keepWithNext=True,
        )
        body = ParagraphStyle(
            "SafeBody", parent=styles["BodyText"], leading=15, spaceAfter=8
        )
        story = [Spacer(1, 34 * mm)]
        if snapshot.branding.logo_path:
            story += [
                Image(
                    snapshot.branding.logo_path,
                    width=40 * mm,
                    height=20 * mm,
                    kind="proportional",
                ),
                Spacer(1, 8 * mm),
            ]
        story += [
            Paragraph(
                _text(snapshot.branding.display_name),
                ParagraphStyle("Org", parent=styles["Title"], textColor=primary),
            ),
            Spacer(1, 18 * mm),
            Paragraph(
                _text(snapshot.proposal["title"]),
                ParagraphStyle(
                    "Cover", parent=styles["Title"], fontSize=28, leading=34
                ),
            ),
            Spacer(1, 8 * mm),
            Paragraph(
                f"Prepared for {_text(snapshot.client['name'])}", styles["Heading2"]
            ),
            Paragraph(
                f"Proposal {_text(snapshot.proposal['number'])}", styles["Heading3"]
            ),
            Paragraph(f"Issue date: {_text(snapshot.proposal['issue_date'])}", body),
        ]
        if snapshot.proposal["valid_until"]:
            story.append(
                Paragraph(
                    f"Valid until: {_text(snapshot.proposal['valid_until'])}", body
                )
            )
        if confidential:
            story += [
                Spacer(1, 20 * mm),
                Paragraph(
                    "CONFIDENTIAL",
                    ParagraphStyle(
                        "Confidential",
                        parent=styles["Heading3"],
                        textColor=primary,
                        alignment=TA_CENTER,
                    ),
                ),
            ]
        story += [
            PageBreak(),
            Paragraph("Proposal Information", heading),
            self._info_table(snapshot),
        ]
        for section in snapshot.sections:
            story += [
                KeepTogether(
                    [
                        Paragraph(_text(section["title"]), heading),
                        Paragraph(
                            _text(section["content"]).replace("\n", "<br/>"), body
                        ),
                    ]
                )
            ]
        if snapshot.items:
            story += [
                Paragraph("Commercial Proposal", heading),
                self._commercial_table(snapshot),
            ]
        contacts = [
            snapshot.branding.website,
            snapshot.branding.email,
            snapshot.branding.phone,
        ]
        if any(contacts):
            story += [
                Paragraph("Contact", heading),
                Paragraph(" | ".join(_text(item) for item in contacts if item), body),
            ]
        if snapshot.branding.footer:
            story.append(Paragraph(_text(snapshot.branding.footer), body))
        doc.build(story)
        return output.getvalue()

    @staticmethod
    def _info_table(snapshot: ProposalPdfSnapshot) -> Table:
        rows = [
            ("Proposal", snapshot.proposal["number"]),
            ("Client", snapshot.client["name"]),
            ("Prepared by", snapshot.branding.display_name),
            ("Issue date", snapshot.proposal["issue_date"]),
            ("Version", "Current"),
            ("Currency", snapshot.proposal["currency"]),
        ]
        table = Table(
            [[_text(a), _text(b)] for a, b in rows], colWidths=[42 * mm, 115 * mm]
        )
        table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (0, -1),
                        colors.HexColor(snapshot.branding.primary_color),
                    ),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    @staticmethod
    def _commercial_table(snapshot: ProposalPdfSnapshot) -> Table:
        styles = getSampleStyleSheet()
        small = ParagraphStyle(
            "Cell", parent=styles["BodyText"], fontSize=8, leading=10
        )
        header = [
            "#",
            "Offering / Description",
            "Qty",
            "Unit Price",
            "Discount",
            "Tax",
            "Total",
        ]
        rows = [header]
        for index, item in enumerate(snapshot.items, 1):
            rows.append(
                [
                    str(index),
                    Paragraph(
                        f"<b>{_text(item['title'])}</b><br/>"
                        f"{_text(item['description'])[:900]}",
                        small,
                    ),
                    _money(item["quantity"]),
                    _money(item["unit_price"]),
                    _money(item["discount"]),
                    _money(item["line_tax"]),
                    _money(item["line_total"]),
                ]
            )
        commercial = snapshot.commercial
        rows += [
            ["", "", "", "", "", "Subtotal", _money(commercial["subtotal"])],
            ["", "", "", "", "", "Discount", _money(commercial["discount"])],
            ["", "", "", "", "", "Tax", _money(commercial["tax"])],
            [
                "",
                "",
                "",
                "",
                "",
                f"Total ({commercial['currency']})",
                _money(commercial["total"]),
            ],
        ]
        table = Table(
            rows,
            repeatRows=1,
            colWidths=[8 * mm, 66 * mm, 12 * mm, 21 * mm, 18 * mm, 17 * mm, 23 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor(snapshot.branding.primary_color),
                    ),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -5), 0.25, colors.grey),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BACKGROUND", (-2, -4), (-1, -1), colors.HexColor("#F3F4F6")),
                    ("FONTNAME", (-2, -1), (-1, -1), "Helvetica-Bold"),
                ]
            )
        )
        return table

    @staticmethod
    def _page(
        canvas: object, doc: object, snapshot: ProposalPdfSnapshot, confidential: bool
    ) -> None:
        if doc.page > 1:
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.grey)
            canvas.drawString(
                18 * mm, 12 * mm, _text(snapshot.branding.display_name)[:70]
            )
            footer = f"{snapshot.proposal['number']} | {'Confidential | ' if confidential else ''}Page {doc.page}"
            canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, footer)
            canvas.restoreState()


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"
