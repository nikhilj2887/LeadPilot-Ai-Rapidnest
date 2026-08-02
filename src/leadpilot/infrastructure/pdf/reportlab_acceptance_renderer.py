from __future__ import annotations

import html
import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from leadpilot.application.proposal_acceptance import (
    AcceptanceEvidence,
    SignatureType,
)


class ReportLabSignedAcceptanceRenderer:
    def render(self, original_pdf: bytes, evidence: AcceptanceEvidence) -> bytes:
        appendix = io.BytesIO()
        styles = getSampleStyleSheet()
        primary = self._color(evidence.tenant_primary_color)
        title = ParagraphStyle(
            "SignedTitle",
            parent=styles["Title"],
            textColor=primary,
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        )
        body = ParagraphStyle(
            "SignedBody", parent=styles["BodyText"], leading=16, spaceAfter=3 * mm
        )
        story: list[object] = [
            Paragraph(html.escape(evidence.tenant_name), title),
            Paragraph(
                "SIGNED COPY",
                ParagraphStyle(
                    "Mark",
                    parent=styles["Heading1"],
                    alignment=TA_CENTER,
                    textColor=colors.HexColor("#15803D"),
                ),
            ),
            Spacer(1, 6 * mm),
            Paragraph(html.escape(evidence.proposal_title), styles["Heading2"]),
            Paragraph(f"Proposal {html.escape(evidence.proposal_number)}", body),
            Paragraph(f"Prepared for {html.escape(evidence.client_name)}", body),
            Spacer(1, 4 * mm),
        ]
        rows = [
            ("Accepted by", evidence.accepted_by_name),
            ("Email", evidence.accepted_by_email),
            ("Company", evidence.accepted_by_company),
            ("Title", evidence.accepted_by_title or "Not provided"),
            ("Accepted at", evidence.accepted_at.isoformat()),
            ("Signature type", evidence.signature_type.value.title()),
        ]
        table = Table(
            [
                [
                    Paragraph(f"<b>{html.escape(label)}</b>", body),
                    Paragraph(html.escape(value), body),
                ]
                for label, value in rows
            ],
            colWidths=(45 * mm, 115 * mm),
            repeatRows=0,
        )
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.extend(
            [table, Spacer(1, 8 * mm), Paragraph("Signature", styles["Heading2"])]
        )
        if (
            evidence.signature_type == SignatureType.HANDWRITTEN
            and evidence.signature_png
        ):
            reader = ImageReader(io.BytesIO(evidence.signature_png))
            width, height = reader.getSize()
            display_width = min(100 * mm, width * 0.3 * mm)
            story.append(
                Image(
                    io.BytesIO(evidence.signature_png),
                    width=display_width,
                    height=display_width * height / width,
                )
            )
        else:
            story.append(
                Paragraph(
                    f"<i>{html.escape(evidence.typed_signature or evidence.accepted_by_name)}</i>",
                    ParagraphStyle(
                        "TypedSignature",
                        parent=styles["Heading2"],
                        fontName="Helvetica-Oblique",
                        fontSize=20,
                    ),
                )
            )
        if evidence.comments:
            story.extend(
                [
                    Spacer(1, 6 * mm),
                    Paragraph("Client comments", styles["Heading2"]),
                    Paragraph(html.escape(evidence.comments), body),
                ]
            )
        story.extend(
            [
                Spacer(1, 8 * mm),
                Paragraph("Evidence hash", styles["Heading3"]),
                Paragraph(
                    html.escape(evidence.evidence_hash),
                    ParagraphStyle(
                        "Hash", parent=body, fontName="Courier", fontSize=8, leading=11
                    ),
                ),
                Paragraph(
                    f"Original proposal checksum: {html.escape(evidence.original_document_checksum)}",
                    ParagraphStyle(
                        "OriginalHash",
                        parent=body,
                        fontName="Courier",
                        fontSize=8,
                        leading=11,
                    ),
                ),
                Spacer(1, 8 * mm),
                Paragraph(
                    "This signed copy combines the immutable proposal PDF with the recorded client acceptance evidence.",
                    body,
                ),
            ]
        )
        SimpleDocTemplate(
            appendix,
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=f"Signed {evidence.proposal_number}",
            author=evidence.tenant_name,
        ).build(story)
        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(original_pdf)).pages:
            writer.add_page(page)
        for page in PdfReader(io.BytesIO(appendix.getvalue())).pages:
            writer.add_page(page)
        writer.add_metadata(
            {
                "/Title": f"Signed {evidence.proposal_number}",
                "/Author": evidence.tenant_name,
                "/Subject": "Signed proposal acceptance evidence",
            }
        )
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    @staticmethod
    def _color(value: str) -> colors.Color:
        try:
            return colors.HexColor(value)
        except (ValueError, TypeError):
            return colors.HexColor("#2563EB")
