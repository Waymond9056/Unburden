"""Build a downloadable prior-auth evidence packet PDF.

Cover sheet + the selected source PDFs, in order. Intended as the artifact a
clinician would review and submit — Unburden does not transmit it to an insurer.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from app.models.db import Document, Patient
from app.services.evidence_packet import (
    EvidencePacket,
    build_evidence_packet,
    build_packet_from_document_ids,
)
from app.services.policy import FICTIONAL_POLICY_ID


def _render_simple_pdf(paragraphs: list[tuple[str, str]]) -> bytes:
    """paragraphs: list of (style_name, html_text)."""
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    story = []
    for style_name, text in paragraphs:
        story.append(Paragraph(text, styles[style_name]))
        story.append(Spacer(1, 8))
    SimpleDocTemplate(buffer, pagesize=letter).build(story)
    return buffer.getvalue()


def _cover_pdf_bytes(patient: Patient, packet: EvidencePacket) -> bytes:
    blocks: list[tuple[str, str]] = [
        ("Title", "PRIOR AUTHORIZATION EVIDENCE PACKET"),
        (
            "Normal",
            "Prepared by Unburden for clinician review and insurer submission packing.",
        ),
        (
            "Normal",
            "This PDF includes a cover sheet followed by the selected supporting medical "
            "documents. Unburden does not transmit this packet to any insurer and does not "
            "approve coverage.",
        ),
        ("Normal", f"<b>Patient:</b> {patient.display_name}"),
        ("Normal", f"<b>Patient ID:</b> {patient.id}"),
        (
            "Normal",
            f"<b>Date of birth:</b> {patient.date_of_birth.isoformat() if patient.date_of_birth else '—'}",
        ),
        ("Normal", f"<b>Policy:</b> {packet.policy_name}"),
        ("Normal", f"<b>Policy ID:</b> {packet.policy_id}"),
        ("Heading2", "Attached supporting documents"),
    ]
    if packet.disclaimer.strip():
        # Insert after the coverage notice, before patient fields.
        blocks.insert(3, ("Normal", packet.disclaimer))

    if not packet.selected_documents:
        blocks.append(
            (
                "Normal",
                "No verified supporting documents were selected for this packet.",
            )
        )
    else:
        for index, doc in enumerate(packet.selected_documents, start=1):
            covers = "; ".join(doc.covers_requirement_titles) or "—"
            blocks.append(
                (
                    "Normal",
                    f"{index}. <b>{doc.source_label}</b> "
                    f"({doc.original_filename}, {doc.page_count} page"
                    f"{'' if doc.page_count == 1 else 's'})",
                )
            )
            blocks.append(("Normal", f"Covers: {covers}"))

    blocks.append(("Heading2", "Still needed before complete submission"))
    if not packet.missing_evidence:
        blocks.append(
            (
                "Normal",
                "No missing documentation items for the current evaluation.",
            )
        )
    else:
        for item in packet.missing_evidence:
            blocks.append(
                (
                    "Normal",
                    f"• <b>{item.title}</b> [{item.status.replace('_', ' ')}]",
                )
            )
            blocks.append(("Normal", item.explanation))
            if item.suggested_document_types:
                blocks.append(
                    (
                        "Normal",
                        "Suggested document type(s): "
                        + "; ".join(item.suggested_document_types),
                    )
                )

    return _render_simple_pdf(blocks)


def _divider_pdf_bytes(*, title: str, filename: str, covers: str) -> bytes:
    return _render_simple_pdf(
        [
            ("Heading1", "ATTACHED SOURCE DOCUMENT"),
            ("Heading2", title),
            ("Normal", filename),
            ("Normal", f"Supports: {covers}"),
        ]
    )


def export_evidence_packet_pdf(
    db: Session,
    patient_id: str,
    *,
    policy_id: str = FICTIONAL_POLICY_ID,
    document_ids: list[str] | None = None,
) -> tuple[bytes, str]:
    """Return (pdf_bytes, filename) for the submission-ready evidence packet."""
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ValueError(f"Patient not found: {patient_id}")

    if document_ids is not None:
        packet = build_packet_from_document_ids(
            db, patient_id, document_ids, policy_id=policy_id
        )
    else:
        packet = build_evidence_packet(db, patient_id, policy_id=policy_id)
    cover_bytes = _cover_pdf_bytes(patient, packet)

    merged = pymupdf.open()
    cover_doc = pymupdf.open(stream=cover_bytes, filetype="pdf")
    merged.insert_pdf(cover_doc)
    cover_doc.close()

    missing_files: list[str] = []
    for item in packet.selected_documents:
        document = db.get(Document, item.document_id)
        if document is None or not Path(document.storage_path).exists():
            missing_files.append(item.original_filename)
            continue

        divider = pymupdf.open(
            stream=_divider_pdf_bytes(
                title=item.source_label,
                filename=item.original_filename,
                covers="; ".join(item.covers_requirement_titles) or "—",
            ),
            filetype="pdf",
        )
        merged.insert_pdf(divider)
        divider.close()

        source = pymupdf.open(document.storage_path)
        merged.insert_pdf(source)
        source.close()

    if missing_files:
        notice = pymupdf.open(
            stream=_render_simple_pdf(
                [
                    ("Heading2", "Missing attached files"),
                    (
                        "Normal",
                        "The following selected documents could not be attached from storage: "
                        + ", ".join(missing_files),
                    ),
                ]
            ),
            filetype="pdf",
        )
        merged.insert_pdf(notice)
        notice.close()

    output = io.BytesIO()
    merged.save(output)
    merged.close()

    safe_patient = "".join(
        ch if ch.isalnum() or ch in "-_" else "-" for ch in patient.display_name
    )
    filename = f"unburden-pa-evidence-packet-{safe_patient or patient_id}.pdf"
    return output.getvalue(), filename
